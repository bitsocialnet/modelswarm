"""Public Hugging Face fallback: pin revisions and verify complete files first.

No requests inherit tokens, cookies, netrc credentials, or proxy environment
variables. This module returns only complete verified local files; the endpoint
owns response streaming and model-format policy.
"""

from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import http.client
import ipaddress
import json
import os
from pathlib import Path
import queue
import re
import socket
import ssl
import tempfile
import threading
import time
from types import MappingProxyType
from typing import Mapping
import unicodedata
from urllib.parse import quote, urljoin, urlsplit

from .cache import _open_regular, cache_root, ensure_directory
from .manifest import MAX_FILE_BYTES, MAX_FILES, NAME_PART, validate_relative_path


MAX_METADATA_BYTES = 16 * 1024 * 1024
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_REVISION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,127}\Z")
_CHUNK = 1024 * 1024


class UpstreamError(Exception):
    def __init__(self, status, message, code="UpstreamError"):
        super().__init__(message)
        self.status = status
        self.message = message
        self.code = code


@dataclass(frozen=True)
class UpstreamFile:
    path: str
    size: int
    digest: str
    algorithm: str

    @property
    def etag(self):
        return self.digest


@dataclass(frozen=True)
class UpstreamModel:
    repo: str
    commit: str
    files: Mapping[str, UpstreamFile]


def validate_repo(repo):
    parts = repo.split("/") if isinstance(repo, str) else []
    if (not 1 <= len(parts) <= 2 or any(not NAME_PART.fullmatch(part) or ".." in part or "--" in part for part in parts)):
        raise UpstreamError(400, "invalid upstream repository identifier", "BadRequest")
    return repo


def validate_revision(revision):
    if (not isinstance(revision, str) or not _REVISION.fullmatch(revision)
            or any(part in ("", ".", "..") or part.endswith(".lock") for part in revision.split("/"))):
        raise UpstreamError(400, "invalid upstream revision", "BadRequest")
    return revision


def _unique_keys(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate metadata JSON key")
        value[key] = item
    return value


def _origin(parts):
    return parts.scheme, parts.hostname, parts.port or (443 if parts.scheme == "https" else 80)


def _new_digest(file):
    if file.algorithm == "sha256":
        return hashlib.sha256()
    return hashlib.sha1(b"blob " + str(file.size).encode("ascii") + b"\0")


class PublicHub:
    def __init__(self, cache, base_url="https://huggingface.co", timeout=30, cancel=None):
        if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or not 0 < timeout <= 3600:
            raise ValueError("upstream timeout must be between 0 and 3600 seconds")
        self.timeout = float(timeout)
        self.cancel = cancel if cancel is not None else threading.Event()
        self.base_url = base_url.rstrip("/")
        self._base = self._parse_url(self.base_url)
        if self._base.query or self._base.fragment:
            raise ValueError("upstream base URL cannot contain a query or fragment")
        self._fixture_origin = None
        if self._base.scheme == "http":
            host = self._base.hostname
            try:
                local = ipaddress.ip_address(host).is_loopback
            except ValueError:
                local = host == "localhost"
            if not local:
                raise ValueError("HTTP upstream is allowed only for an explicitly configured loopback fixture")
            self._fixture_origin = _origin(self._base)
        self.cache = cache_root(cache) / ".modelswarm-upstream" / hashlib.sha256(self.base_url.encode()).hexdigest()
        self._context = ssl.create_default_context()
        self._models = OrderedDict()
        self._lock = threading.Lock()

    @staticmethod
    def _parse_url(url):
        if (not isinstance(url, str) or not url or len(url) > 8192 or "\\" in url
                or any(ord(char) < 32 or ord(char) == 127 for char in url)):
            raise ValueError("invalid upstream URL")
        parts = urlsplit(url)
        if (parts.scheme not in ("https", "http") or not parts.hostname or parts.username is not None
                or parts.password is not None or parts.fragment or (parts.port is not None and not 1 <= parts.port <= 65535)):
            raise ValueError("upstream URL requires HTTP(S), a hostname, and no credentials or fragment")
        return parts

    def _remaining(self, deadline):
        if self.cancel.is_set():
            raise UpstreamError(503, "upstream request cancelled", "UpstreamCancelled")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise UpstreamError(504, "upstream request exceeded its total time limit", "UpstreamTimeout")
        return remaining

    def _addresses(self, host, port, deadline, local):
        # getaddrinfo has no timeout API. A daemon resolver lets the request
        # honor its deadline/cancellation even if the system resolver stalls.
        resolved = queue.Queue(maxsize=1)

        def resolve():
            try:
                resolved.put(socket.getaddrinfo(host, port, type=socket.SOCK_STREAM))
            except OSError as error:
                resolved.put(error)

        threading.Thread(target=resolve, daemon=True).start()
        while True:
            try:
                result = resolved.get(timeout=min(0.1, self._remaining(deadline)))
                break
            except queue.Empty:
                continue
        if isinstance(result, Exception):
            raise result
        if not result:
            raise UpstreamError(502, "upstream hostname has no addresses", "UpstreamUnavailable")
        for _, _, _, _, address in result:
            ip = ipaddress.ip_address(address[0])
            if not (ip.is_loopback if local else ip.is_global):
                raise UpstreamError(502, "upstream target is not an allowed public/fixture address", "UnsafeUpstream")
        return result

    def _connect(self, parts, deadline):
        local = parts.scheme == "http" and self._fixture_origin is not None and _origin(parts) == self._fixture_origin
        if parts.scheme != "https" and not local:
            raise UpstreamError(502, "upstream redirect must use public HTTPS or the configured loopback origin", "UnsafeUpstream")
        port = parts.port or (443 if parts.scheme == "https" else 80)
        addresses = self._addresses(parts.hostname, port, deadline, local)
        error = None
        for family, kind, protocol, _, address in addresses:
            raw = socket.socket(family, kind, protocol)
            try:
                raw.settimeout(min(10, self._remaining(deadline)))
                # Connect to the validated address rather than resolving again.
                raw.connect(address)
                if parts.scheme == "https":
                    raw = self._context.wrap_socket(raw, server_hostname=parts.hostname)
                if parts.scheme == "https":
                    connection = http.client.HTTPSConnection(parts.hostname, port, timeout=min(10, self._remaining(deadline)), context=self._context)
                else:
                    connection = http.client.HTTPConnection(parts.hostname, port, timeout=min(10, self._remaining(deadline)))
                connection.sock = raw
                return connection, raw
            except OSError as caught:
                raw.close()
                error = caught
            except BaseException:
                raw.close()
                raise
        raise error or OSError("upstream connection failed")

    @contextmanager
    def _response(self, url, deadline):
        for _ in range(6):
            connection = response = None
            stop = threading.Event()
            watcher = None
            try:
                self._remaining(deadline)
                try:
                    parts = self._parse_url(url)
                except ValueError as error:
                    raise UpstreamError(502, "upstream returned an unsafe redirect", "UnsafeUpstream") from error
                connection, active_socket = self._connect(parts, deadline)

                def interrupt_io():
                    while not stop.wait(0.05):
                        if self.cancel.is_set() or time.monotonic() >= deadline:
                            try:
                                active_socket.shutdown(socket.SHUT_RDWR)
                            except OSError:
                                pass
                            return

                watcher = threading.Thread(target=interrupt_io, daemon=True)
                watcher.start()
                target = parts.path or "/"
                if parts.query:
                    target += "?" + parts.query
                connection.request("GET", target, headers={"User-Agent": "modelswarm/0.0.1", "Accept-Encoding": "identity", "Connection": "close"})
                response = connection.getresponse()
                self._remaining(deadline)
                if response.status in (301, 302, 303, 307, 308):
                    location = response.getheader("Location")
                    if not location:
                        raise UpstreamError(502, "upstream redirect has no target", "UpstreamUnavailable")
                    url = urljoin(url, location)
                    continue
                if response.status != 200:
                    code = response.getheader("X-Error-Code")
                    known = {"RepoNotFound", "RevisionNotFound", "EntryNotFound", "GatedRepo"}
                    if code not in known:
                        code = "RepoNotFound" if response.status == 404 else "UpstreamUnavailable"
                    status = response.status if response.status in (401, 403, 404, 429) else 502
                    raise UpstreamError(status, f"public upstream request failed ({response.status}, {code})", code)
                if response.getheader("Content-Encoding", "identity").lower() != "identity":
                    raise UpstreamError(502, "compressed upstream response is unsupported", "UpstreamVerificationError")
                yield response
                self._remaining(deadline)
                return
            except UpstreamError:
                raise
            except (OSError, http.client.HTTPException) as error:
                self._remaining(deadline)
                status = 504 if isinstance(error, TimeoutError) else 502
                raise UpstreamError(status, "public upstream connection failed", "UpstreamUnavailable") from error
            finally:
                stop.set()
                if response is not None:
                    response.close()
                if connection is not None:
                    connection.close()
                if watcher is not None:
                    watcher.join(timeout=0.2)
        raise UpstreamError(502, "upstream exceeded the redirect limit", "UpstreamUnavailable")

    @staticmethod
    def _content_length(response):
        value = response.getheader("Content-Length")
        if value is None:
            return None
        try:
            if not value.isdecimal():
                raise ValueError
            return int(value)
        except ValueError as error:
            raise UpstreamError(502, "upstream Content-Length is invalid", "UpstreamVerificationError") from error

    def metadata(self, repo, revision="main"):
        validate_repo(repo)
        validate_revision(revision)
        if _COMMIT.fullmatch(revision):
            with self._lock:
                cached = self._models.get((repo, revision))
                if cached is not None:
                    self._models.move_to_end((repo, revision))
                    return cached
        deadline = time.monotonic() + self.timeout
        url = f"{self.base_url}/api/models/{quote(repo, safe='/')}/revision/{quote(revision, safe='')}?blobs=true"
        with self._response(url, deadline) as response:
            length = self._content_length(response)
            if length is not None and length > MAX_METADATA_BYTES:
                raise UpstreamError(502, "upstream metadata exceeds the size limit", "UpstreamMetadataError")
            encoded = bytearray()
            while True:
                self._remaining(deadline)
                block = response.read(min(_CHUNK, MAX_METADATA_BYTES + 1 - len(encoded)))
                if not block:
                    break
                encoded.extend(block)
                if len(encoded) > MAX_METADATA_BYTES:
                    raise UpstreamError(502, "upstream metadata exceeds the size limit", "UpstreamMetadataError")
        try:
            data = json.loads(encoded, object_pairs_hook=_unique_keys)
            commit = data["sha"]
            siblings = data["siblings"]
            if not isinstance(commit, str) or not _COMMIT.fullmatch(commit):
                raise ValueError("upstream has no full commit SHA")
            if _COMMIT.fullmatch(revision) and commit != revision:
                raise ValueError("upstream returned a different commit")
            if not isinstance(siblings, list) or len(siblings) > MAX_FILES:
                raise ValueError("invalid or excessive upstream file list")
            files, path_keys = {}, set()
            for sibling in siblings:
                path = validate_relative_path(sibling["rfilename"])
                key = unicodedata.normalize("NFC", path).casefold()
                if key in path_keys:
                    raise ValueError("duplicate or colliding upstream file path")
                path_keys.add(key)
                size = sibling["size"]
                if type(size) is not int or not 0 <= size <= MAX_FILE_BYTES:
                    raise ValueError("upstream file has invalid size")
                lfs = sibling.get("lfs")
                if lfs is not None:
                    digest = lfs["sha256"]
                    if (not isinstance(digest, str) or not _SHA256.fullmatch(digest)
                            or type(lfs["size"]) is not int or lfs["size"] != size):
                        raise ValueError("upstream LFS digest/size is invalid")
                    algorithm = "sha256"
                else:
                    digest = sibling["blobId"]
                    if not isinstance(digest, str) or not _COMMIT.fullmatch(digest):
                        raise ValueError("upstream Git blob digest is invalid")
                    algorithm = "git-sha1"
                files[path] = UpstreamFile(path, size, digest, algorithm)
            for path in path_keys:
                if any("/".join(path.split("/")[:index]) in path_keys for index in range(1, len(path.split("/")))):
                    raise ValueError("upstream file collides with another file's directory")
        except (ValueError, KeyError, TypeError, UnicodeError, RecursionError) as error:
            raise UpstreamError(502, f"invalid upstream metadata: {error}", "UpstreamMetadataError") from error
        model = UpstreamModel(repo, commit, MappingProxyType(files))
        with self._lock:
            self._models[(repo, commit)] = model
            self._models.move_to_end((repo, commit))
            while len(self._models) > 16:
                self._models.popitem(last=False)
        return model

    def _verify_cached(self, path, file, deadline):
        digest, size = _new_digest(file), 0
        with _open_regular(path) as stream:
            while True:
                self._remaining(deadline)
                block = stream.read(_CHUNK)
                if not block:
                    break
                size += len(block)
                if size > file.size:
                    break
                digest.update(block)
        if size != file.size or digest.hexdigest() != file.digest:
            raise UpstreamError(502, "cached upstream file failed digest/size verification", "UpstreamVerificationError")

    def obtain(self, repo, commit, path):
        deadline = time.monotonic() + self.timeout
        validate_repo(repo)
        if not isinstance(commit, str) or not _COMMIT.fullmatch(commit):
            raise UpstreamError(400, "upstream file fetch requires a full pinned commit SHA", "BadRequest")
        try:
            validate_relative_path(path)
        except ValueError as error:
            raise UpstreamError(400, str(error), "BadRequest") from error
        model = self.metadata(repo, commit)
        file = model.files.get(path)
        if file is None:
            raise UpstreamError(404, "file is absent from the pinned upstream revision", "EntryNotFound")
        self._remaining(deadline)
        blobs = ensure_directory(self.cache / "blobs")
        blob = blobs / f"{file.algorithm}-{file.digest}"
        if os.path.lexists(blob):
            try:
                self._verify_cached(blob, file, deadline)
            except (OSError, ValueError) as error:
                raise UpstreamError(502, "upstream cache path is unsafe or unreadable", "UpstreamVerificationError") from error
            return blob, file
        descriptor, temporary_name = tempfile.mkstemp(prefix=".incoming-", dir=blobs)
        temporary = Path(temporary_name)
        try:
            digest, size = _new_digest(file), 0
            url = f"{self.base_url}/{quote(repo, safe='/')}/resolve/{commit}/{quote(path, safe='/')}"
            with os.fdopen(descriptor, "wb") as output:
                with self._response(url, deadline) as response:
                    length = self._content_length(response)
                    if length is not None and length != file.size:
                        raise UpstreamError(502, "upstream file size differs from pinned metadata", "UpstreamVerificationError")
                    while True:
                        self._remaining(deadline)
                        block = response.read(min(_CHUNK, file.size + 1 - size))
                        if not block:
                            break
                        size += len(block)
                        if size > file.size:
                            raise UpstreamError(502, "upstream file exceeds its pinned size", "UpstreamVerificationError")
                        digest.update(block)
                        output.write(block)
                if size != file.size or digest.hexdigest() != file.digest:
                    raise UpstreamError(502, "upstream file failed digest/size verification", "UpstreamVerificationError")
                output.flush()
                os.fsync(output.fileno())
            try:
                os.link(temporary, blob, follow_symlinks=False)
            except FileExistsError:
                self._verify_cached(blob, file, deadline)
            return blob, file
        finally:
            temporary.unlink(missing_ok=True)
