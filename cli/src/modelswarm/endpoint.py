"""A bounded, loopback-only subset of the read-only Hugging Face model API."""

from dataclasses import dataclass
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from pathlib import Path
import re
import signal
import socket
import tempfile
import threading
from urllib.parse import quote, unquote, urlsplit, parse_qs

from .cache import cache_root, ensure_directory, snapshot_revision
from .engine import InterruptedDownload, check_file, peer_address
from .formats import (TEXT_NAMES, TEXT_SUFFIXES, detect_format, is_flagged,
                      is_flagged_path)
from .manifest import load_manifest, validate_relative_path
from .upstream import PublicHub, UpstreamError


@dataclass(frozen=True)
class File:
    path: str
    size: int
    digest: str
    algorithm: str = "sha256"


@dataclass
class Model:
    repo: str
    commit: str
    files: dict
    source: str


def data_filename(path):
    name = Path(path)
    return (not is_flagged_path(path) and (name.suffix.casefold() in
            TEXT_SUFFIXES | {".json", ".gguf", ".safetensors"}
            or name.name.casefold() in TEXT_NAMES))


class Endpoint:
    def __init__(self, args, emit):
        self.args, self.emit = args, emit
        self.cache = ensure_directory(cache_root(args.cache_dir))
        self.cancel = threading.Event()
        self.transfers = threading.Lock()
        self.registered = {}
        self.provenance = {}
        # Freeze manifests at startup; request workers never reread mutable input.
        self.scratch = tempfile.TemporaryDirectory(prefix="endpoint-", dir=ensure_directory(self.cache / ".modelswarm"))
        try:
            for path in args.manifest:
                manifest, digest = load_manifest(path)
                if manifest["name"] in self.registered:
                    raise ValueError("register at most one manifest per model name")
                self.registered[manifest["name"]] = (manifest, digest)
            from .releases import resolve
            for uri in args.release:
                manifest, digest, provenance = resolve(uri, rpc=args.rpc, timeout=args.rpc_timeout,
                                                      allow_local=args.allow_local_sources)
                if manifest["name"] in self.registered:
                    raise ValueError("register at most one manifest or release per model name")
                self.registered[manifest["name"]] = (manifest, digest)
                self.provenance[manifest["name"]] = provenance
            self.upstream = None if args.no_upstream else PublicHub(self.cache, base_url=args.upstream, timeout=args.timeout, cancel=self.cancel)
        except Exception:
            self.scratch.cleanup()
            raise

    def close(self):
        self.cancel.set()
        self.scratch.cleanup()

    def model(self, repo, revision):
        if repo in self.registered:
            manifest, digest = self.registered[repo]
            commit = snapshot_revision(digest)
            if revision not in ("main", manifest["version"], commit):
                raise UpstreamError(404, "Revision is not registered locally", "RevisionNotFound")
            files = {entry["path"]: File(entry["path"], entry["size"], entry["sha256"])
                     for entry in manifest["files"] if self.args.allow_unsafe or
                     not (is_flagged(entry["format"]) or is_flagged_path(entry["path"]))}
            return Model(repo, commit, files, "local")
        if self.upstream is None:
            raise UpstreamError(404, "Model is not registered; upstream fallback is disabled", "RepoNotFound")
        remote = self.upstream.metadata(repo, revision)
        files = {path: File(path, entry.size, entry.digest, entry.algorithm)
                 for path, entry in remote.files.items() if self.args.allow_unsafe or data_filename(path)}
        return Model(repo, remote.commit, files, "upstream")

    def entry(self, model, path):
        validate_relative_path(path)
        if path not in model.files:
            if model.source == "local":
                entries = self.registered[model.repo][0]["files"]
                flagged = any(entry["path"] == path for entry in entries)
            else:
                flagged = path in self.upstream.metadata(model.repo, model.commit).files
            if flagged:
                raise UpstreamError(403, "File is excluded by format policy; restart with --allow-unsafe to opt in", "FormatBlocked")
            raise UpstreamError(404, "File is absent at this revision", "EntryNotFound")
        return model.files[path]

    def obtain(self, model, entry):
        # One transfer at a time bounds disk/network load and serializes snapshot
        # extension. HTTP metadata and already-open responses remain concurrent.
        with self.transfers:
            if self.cancel.is_set():
                raise UpstreamError(503, "Endpoint is shutting down", "Unavailable")
            if model.source == "local":
                from .cli import pull_release
                manifest, digest = self.registered[model.repo]
                selected = next(item for item in manifest["files"] if item["path"] == entry.path)
                result = pull_release(manifest, digest, [selected], [], self.cache,
                                      peers=self.args.peer, discovery=not self.args.no_discovery,
                                      timeout=self.args.timeout, rate=self.args.rate_limit,
                                      checkpoint_interval=self.args.checkpoint_interval,
                                      cancel=self.cancel, emit=self.emit,
                                      allow_local_sources=model.repo not in self.provenance or self.args.allow_local_sources)
                path = Path(result["snapshot"]) / entry.path
                check_file(selected, path)
                return path
            path, actual = self.upstream.obtain(model.repo, model.commit, entry.path)
            if (actual.size, actual.digest, actual.algorithm) != (entry.size, entry.digest, entry.algorithm):
                raise UpstreamError(502, "Pinned upstream metadata changed", "IntegrityError")
            # Preserve the original suffix for conservative inspection without
            # copying a potentially large verified blob.
            with tempfile.TemporaryDirectory(prefix="inspect-", dir=self.scratch.name) as directory:
                named = Path(directory) / Path(entry.path).name
                named.symlink_to(path)
                detected = detect_format(named)
            if not self.args.allow_unsafe and is_flagged(detected):
                raise UpstreamError(403, "Downloaded file is excluded by format policy", "FormatBlocked")
            return path


def range_bounds(value, size):
    if not value:
        return 0, size - 1, False
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", value)
    if not match or not any(match.groups()) or size == 0:
        raise ValueError("unsatisfiable byte range")
    first, last = match.groups()
    if not first:
        suffix = int(last)
        if suffix == 0:
            raise ValueError("unsatisfiable byte range")
        return max(0, size - suffix), size - 1, True
    start, end = int(first), min(int(last), size - 1) if last else size - 1
    if start > end or start >= size:
        raise ValueError("unsatisfiable byte range")
    return start, end, True


def _decode(value):
    return unquote(value, encoding="utf-8", errors="strict")


def _repo(parts):
    if len(parts) not in (1, 2):
        raise ValueError("expected a model identifier")
    decoded = [_decode(part) for part in parts]
    if any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}", part)
           or ".." in part or "--" in part for part in decoded):
        raise ValueError("invalid model identifier")
    return "/".join(decoded)


def handler_for(backend):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "Modelswarm/0.0.1"

        def setup(self):
            super().setup()
            self.connection.settimeout(30)

        def log_message(self, *_):
            pass

        def send_response(self, code, message=None):
            self.status = code
            super().send_response(code, message)

        def respond_headers(self, status, length, content_type="application/json", **headers):
            self.send_response(status)
            self.send_header("Content-Length", str(length))
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            # No cookie, auth, CORS or Xet headers are relayed from upstream.
            for key, value in headers.items():
                self.send_header(key.replace("_", "-"), str(value))
            self.end_headers()
            self.response_started = True

        def json(self, value, status=200, **headers):
            data = json.dumps(value).encode()
            self.respond_headers(status, len(data), **headers)
            if self.command != "HEAD":
                self.wfile.write(data)

        def error(self, status, message, code="BadRequest", **headers):
            if getattr(self, "response_started", False):
                self.close_connection = True
                return
            if getattr(self, "commit", None):
                headers.setdefault("X_Repo_Commit", self.commit)
            self.json({"error": message}, status, X_Error_Code=code, **headers)

        def do_HEAD(self):
            self.handle_request()

        def do_GET(self):
            self.handle_request()

        def do_POST(self):
            self.close_connection = True
            self.error(405, "Only GET and HEAD are supported", "MethodNotAllowed", Allow="GET, HEAD")

        def handle_request(self):
            self.status, self.source, self.response_started, self.commit = 500, None, False, None
            try:
                if backend.cancel.is_set():
                    self.close_connection = True
                    raise UpstreamError(503, "Endpoint is shutting down", "Unavailable")
                authority = f"127.0.0.1:{self.server.server_port}"
                if self.headers.get("Host") not in {authority, f"localhost:{self.server.server_port}"}:
                    raise UpstreamError(403, "Unexpected Host header", "Forbidden")
                if self.headers.get("Sec-Fetch-Site") not in (None, "same-origin", "none"):
                    raise UpstreamError(403, "Cross-site browser requests are not supported", "Forbidden")
                origin = self.headers.get("Origin")
                if origin and origin not in {f"http://{authority}", f"http://localhost:{self.server.server_port}"}:
                    raise UpstreamError(403, "Cross-origin browser requests are not supported", "Forbidden")
                if self.headers.get("Transfer-Encoding") or self.headers.get("Content-Length", "0") != "0":
                    self.close_connection = True
                    raise UpstreamError(400, "Request bodies are not supported", "BadRequest")
                parsed = urlsplit(self.path)
                if parsed.scheme or parsed.netloc or len(self.path) > 8192:
                    raise ValueError("invalid request target")
                parts = parsed.path.strip("/").split("/")
                if parts == ["health"]:
                    self.json({"ok": True})
                    return
                if parts[:2] == ["api", "models"]:
                    self.api(parts[2:], parse_qs(parsed.query))
                    return
                # The literal resolve segment follows a one- or two-part repo ID.
                pivot = 2 if len(parts) > 2 and parts[2] == "resolve" else 1
                if len(parts) <= pivot + 2 or parts[pivot] != "resolve":
                    raise UpstreamError(404, "Unsupported endpoint", "NotFound")
                repo, revision = _repo(parts[:pivot]), _decode(parts[pivot + 1])
                relative = validate_relative_path(_decode("/".join(parts[pivot + 2:])))
                model = backend.model(repo, revision)
                self.source, self.commit = model.source, model.commit
                entry = backend.entry(model, relative)
                if revision != model.commit:
                    location = f"/{quote(repo, safe='/')}/resolve/{model.commit}/{quote(relative, safe='/')}"
                    self.respond_headers(307, 0, Location=location, X_Repo_Commit=model.commit,
                                 ETag=f'"{entry.digest}"', X_Linked_Size=entry.size)
                    return
                self.file(model, entry)
            except UpstreamError as error:
                self.error(error.status, str(error), error.code)
            except (ValueError, UnicodeError) as error:
                self.error(400, str(error))
            except InterruptedDownload:
                self.error(503, "Endpoint is shutting down", "Unavailable")
            except (TimeoutError, socket.timeout):
                self.error(504, "Download or upstream request timed out", "Timeout")
            except (BrokenPipeError, ConnectionResetError):
                pass
            except (OSError, RuntimeError) as error:
                backend.emit("request_failed", error=type(error).__name__)
                self.error(502, "Unable to obtain verified content; see server log", "DownloadError")
            finally:
                backend.emit("request", method=self.command, path=urlsplit(self.path).path,
                             status=self.status, source=self.source)

        def api(self, parts, query):
            pivot = next((i for i in (2, 1) if len(parts) > i + 1
                          and parts[i] in ("revision", "tree")), None)
            if pivot is None:
                repo, revision, operation, subpath = _repo(parts), "main", "info", ""
            else:
                repo = _repo(parts[:pivot])
                if len(parts) <= pivot + 1:
                    raise ValueError("revision is required")
                revision = _decode(parts[pivot + 1])
                operation = "info" if parts[pivot] == "revision" else "tree"
                subpath = _decode("/".join(parts[pivot + 2:]))
                if operation == "info" and subpath:
                    raise ValueError("invalid model-info path")
                if subpath:
                    validate_relative_path(subpath)
            model = backend.model(repo, revision)
            self.source, self.commit = model.source, model.commit
            if operation == "info":
                self.json({"id": repo, "sha": model.commit, "private": False, "gated": False,
                           "siblings": [{"rfilename": f.path, "size": f.size, "blobId": f.digest,
                                         **({"lfs": {"sha256": f.digest, "size": f.size, "pointerSize": 0}}
                                            if f.algorithm == "sha256" else {})}
                                        for f in model.files.values()]})
                return
            recursive = query.get("recursive", ["false"])[0].lower() == "true"
            prefix, output, directories = subpath + "/" if subpath else "", [], set()
            for file in model.files.values():
                if not file.path.startswith(prefix):
                    continue
                remainder = file.path[len(prefix):]
                parents = remainder.split("/")[:-1]
                for i in range(len(parents) if recursive else min(1, len(parents))):
                    directories.add(prefix + "/".join(parents[:i + 1]))
                if recursive or not parents:
                    output.append({"type": "file", "oid": file.digest, "path": file.path, "size": file.size,
                                   **({"lfs": {"oid": file.digest, "size": file.size, "pointerSize": 0}}
                                      if file.algorithm == "sha256" else {})})
            if subpath and not output and not directories:
                raise UpstreamError(404, "Directory is absent at this revision", "EntryNotFound")
            output.extend({"type": "directory", "oid": hashlib.sha1(path.encode()).hexdigest(), "path": path, "size": 0}
                          for path in directories)
            self.json(sorted(output, key=lambda item: item["path"]))

        def file(self, model, entry):
            headers = {"X_Repo_Commit": model.commit, "ETag": f'"{entry.digest}"',
                       "Accept_Ranges": "bytes", "X_Modelswarm_Source": model.source,
                       "X_Modelswarm_Verification": "manifest-sha256" if model.source == "local" else entry.algorithm}
            provenance = backend.provenance.get(model.repo)
            if provenance:
                headers["X_Modelswarm_Publisher"] = provenance["publisher"]
                headers["X_Modelswarm_Release"] = provenance["release_cid"]
            value = self.headers.get("Range") if self.command == "GET" else None
            if self.headers.get("If-Range") not in (None, headers["ETag"]):
                value = None
            try:
                start, end, partial = range_bounds(value, entry.size)
            except ValueError:
                self.error(416, "Unsatisfiable byte range", "RangeNotSatisfiable", Content_Range=f"bytes */{entry.size}")
                return
            if partial:
                headers["Content_Range"] = f"bytes {start}-{end}/{entry.size}"
            if self.command == "HEAD":
                self.respond_headers(200, entry.size, "application/octet-stream", **headers)
                return
            path = backend.obtain(model, entry)
            # Open before sending status: failures cannot produce a success body.
            with path.open("rb") as stream:
                stream.seek(start)
                remaining = end - start + 1
                self.respond_headers(206 if partial else 200, remaining, "application/octet-stream", **headers)
                while remaining:
                    block = stream.read(min(1024 * 1024, remaining))
                    if not block:
                        self.close_connection = True
                        return
                    self.wfile.write(block)
                    remaining -= len(block)

    return Handler


class Server(ThreadingHTTPServer):
    daemon_threads = False
    block_on_close = True

    def __init__(self, address, handler):
        self.slots = threading.BoundedSemaphore(16)
        self.connections = set()
        self.connection_lock = threading.Lock()
        super().__init__(address, handler)

    def process_request(self, request, client_address):
        # Reject excess sockets without spawning unbounded request threads.
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        with self.connection_lock:
            self.connections.add(request)
        try:
            super().process_request(request, client_address)
        except Exception:
            with self.connection_lock:
                self.connections.discard(request)
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            with self.connection_lock:
                self.connections.discard(request)
            self.slots.release()

    def server_close(self):
        # Close keep-alive sockets before joining handlers, including clients
        # that keep sending requests and never reach the idle timeout.
        with self.connection_lock:
            connections = list(self.connections)
        for connection in connections:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        super().server_close()


def serve(args):
    from .cli import progress
    if args.host != "127.0.0.1":
        raise ValueError("serve supports only --host 127.0.0.1")
    if not 0 <= args.port <= 65535:
        raise ValueError("port must be between 0 and 65535")
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        raise ValueError("timeout must be finite and positive")
    if not math.isfinite(args.checkpoint_interval) or args.checkpoint_interval < 1:
        raise ValueError("checkpoint interval must be finite and at least one second")
    if not 0 <= args.rate_limit <= 2**31 - 1:
        raise ValueError("rate limit must be between 0 and 2147483647")
    args.peer = [peer_address(value) for value in args.peer]
    backend = Endpoint(args, progress)
    server, handlers = None, {}
    try:
        server = Server((args.host, args.port), handler_for(backend))
        server.timeout = 0.2
        for signum in (signal.SIGINT, signal.SIGTERM):
            handlers[signum] = signal.signal(signum, lambda *_: backend.cancel.set())
        print(json.dumps({"event": "server_ready", "endpoint": f"http://127.0.0.1:{server.server_port}",
                          "registered_models": sorted(backend.registered), "upstream": not args.no_upstream}), flush=True)
        while not backend.cancel.is_set():
            server.handle_request()
    finally:
        if server:
            server.server_close()
        backend.close()
        for signum, handler in handlers.items():
            signal.signal(signum, handler)
    return {"command": "serve", "stopped": True}
