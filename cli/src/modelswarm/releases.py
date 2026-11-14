"""Publisher release selection and the native PKC subprocess boundary."""

import hashlib
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import tempfile
import threading
import time
from urllib.parse import unquote, urlsplit

from .cache import ensure_directory
from .manifest import MAX_MANIFEST_BYTES, load_manifest, validate_source_url
from .upstream import PublicHub, UpstreamError


BRIDGE = Path(__file__).parent / "bridge" / "index.mjs"
PEER_ID = r"12D3KooW[1-9A-HJ-NP-Za-km-z]{44}"
KEY_SCHEMA = "modelswarm/key/v0"
# The pinned PKC RPC fetchCid API does not expose its 1 MiB override.
MAX_IPFS_MANIFEST_BYTES = 1024 * 1024


def rpc_url(value=None):
    value = value or os.environ.get("MODELSWARM_RPC")
    if not value:
        raise ValueError("set --rpc or MODELSWARM_RPC to your PKC node; no hosted Forge endpoint is assumed")
    if not isinstance(value, str) or len(value) > 8192 or any(ord(c) < 33 for c in value):
        raise ValueError("invalid PKC RPC URL")
    parts = urlsplit(value)
    if (parts.scheme not in ("ws", "wss") or not parts.hostname or parts.username
            or parts.password or parts.fragment):
        raise ValueError("RPC requires a ws/wss URL without userinfo or a fragment")
    if parts.scheme == "ws" and parts.hostname not in ("localhost", "127.0.0.1", "::1"):
        raise ValueError("remote RPC requires wss://")
    return value


def bridge(request, timeout=120):
    if not math.isfinite(timeout) or not 0 < timeout <= 3600:
        raise ValueError("PKC timeout must be finite and between 0 and 3600 seconds")
    executable = os.environ.get("MODELSWARM_NODE") or shutil.which("node")
    if not executable or not (BRIDGE.parent / "node_modules" / "@pkcprotocol" / "pkc-js").exists():
        raise ValueError("install Node and the pinned PKC bridge dependencies; see cli/RELEASES.md")
    environment = {key: value for key, value in os.environ.items()
                   if key not in ("DEBUG", "PKC_LOG_LEVEL", "NODE_OPTIONS")}
    # CLI startup resolves profiles before serve installs its own signal handlers.
    # Keep cancellation scoped to this child so a terminated CLI cannot publish
    # later from a detached bridge process.
    previous_terminate = None
    process = None
    if threading.current_thread() is threading.main_thread():
        previous_terminate = signal.getsignal(signal.SIGTERM)

        def terminate(_signum, _frame):
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
            raise KeyboardInterrupt

        signal.signal(signal.SIGTERM, terminate)
    try:
        process = subprocess.Popen([executable, "--max-old-space-size=512", str(BRIDGE)],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, env=environment, start_new_session=True)
        output, _ = process.communicate(json.dumps({**request, "timeout": timeout}), timeout=timeout + 8)
    except (subprocess.TimeoutExpired, KeyboardInterrupt):
        raise ValueError("PKC operation interrupted or timed out; a publish or renewal may have succeeded; check before retrying")
    finally:
        if process is not None and process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.communicate()
        if previous_terminate is not None:
            signal.signal(signal.SIGTERM, previous_terminate)
    if len(output.encode()) > 2 * MAX_MANIFEST_BYTES + 1024 * 1024:
        raise ValueError("PKC bridge response exceeds limit")
    try:
        result = json.loads(output)
    except (ValueError, TypeError) as error:
        raise ValueError("PKC bridge failed; check Node version and installed native dependencies") from error
    if process.returncode or not result.get("ok"):
        raise ValueError(result.get("error", "PKC operation failed"))
    return result


def keygen(args):
    output = args.output.absolute()
    if output.exists() or output.is_symlink():
        raise ValueError("key output already exists; refusing to replace it")
    ensure_directory(output.parent)
    result = bridge({"op": "keygen"}, args.rpc_timeout)
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(descriptor, "w") as stream:
        json.dump({"schema": KEY_SCHEMA, "type": "ed25519", "privateKey": result["privateKey"]}, stream)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    return {"command": "keygen", "key_file": str(output), "publisher": result["publisher"]}


def read_key(path):
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > 4096:
        raise ValueError("key must be a small private regular file, not a symlink or hardlink")
    if os.name == "posix" and (before.st_mode & 0o077 or before.st_uid != os.getuid()):
        raise ValueError("key file must be owned by you with mode 0600")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(descriptor) as stream:
        after = os.fstat(stream.fileno())
        if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
            raise ValueError("key changed while opening")
        value = json.loads(stream.read(4097))
    if (not isinstance(value, dict) or set(value) != {"schema", "type", "privateKey"}
            or value["schema"] != KEY_SCHEMA or value["type"] != "ed25519"
            or not isinstance(value["privateKey"], str) or not re.fullmatch(r"[A-Za-z0-9+/]{43}", value["privateKey"])):
        raise ValueError("invalid Modelswarm Ed25519 key file")
    return value["privateKey"]


def profile_init(args):
    result = bridge({"op": "profile-init", "privateKey": read_key(args.key), "rpc": rpc_url(args.rpc)}, args.rpc_timeout)
    return {"command": "profile-init", "publisher": result["publisher"], "minter": result["minter"], "started": result["started"]}


def profile_start(args):
    if not re.fullmatch(PEER_ID, args.publisher):
        raise ValueError("publisher must be an Ed25519 Peer ID")
    result = bridge({"op": "profile-start", "publisher": args.publisher, "rpc": rpc_url(args.rpc)}, args.rpc_timeout)
    return {"command": "profile-start", "publisher": result["publisher"], "minter": result["minter"], "started": result["started"]}


def profile_renew(args):
    if not re.fullmatch(PEER_ID, args.minter):
        raise ValueError("minter must be the Ed25519 Peer ID printed by profile-init")
    result = bridge({"op": "profile-renew", "privateKey": read_key(args.key), "minter": args.minter,
                     "rpc": rpc_url(args.rpc)}, args.rpc_timeout)
    return {"command": "profile-renew", "publisher": result["publisher"], "minter": result["minter"],
            "sequence": result["sequence"], "previous_sequence": result["previousSequence"]}


def parse_uri(value):
    parts = urlsplit(value)
    # Use netloc verbatim: URL hostname normalization would corrupt Base58 keys.
    if (parts.scheme != "pkc" or not re.fullmatch(PEER_ID, parts.netloc)
            or parts.query or "@" not in parts.path or "%" in parts.netloc
            or ("#" in value and not parts.fragment)):
        raise ValueError("release URI must be pkc://PUBLISHER/owner/model@VERSION[#CID]")
    name, version = unquote(parts.path.lstrip("/")).rsplit("@", 1)
    if (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}/[A-Za-z0-9][A-Za-z0-9_.-]{0,95}", name)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", version)):
        raise ValueError("release URI requires an explicit safe model name and version")
    return {"publisher": parts.netloc, "name": name, "version": version, "cid": parts.fragment or None}


def release_uri(publisher, release, cid):
    return f"pkc://{publisher}/{release['name']}@{release['version']}#{cid}"


def check_source_policy(manifest, allow_local):
    if allow_local:
        return
    for entry in manifest["files"]:
        for source in entry["sources"]:
            parts = urlsplit(source["url"])
            if parts.scheme != "https" or parts.hostname == "localhost":
                raise ValueError("signed releases require public HTTPS sources unless --allow-local-sources is explicit")
            try:
                address = ipaddress.ip_address(parts.hostname)
            except ValueError:
                continue
            if not address.is_global:
                raise ValueError("signed release contains a private network source")


def manifest_from_reference(reference, *, rpc, timeout, allow_local):
    url = reference["url"]
    if url.startswith("ipfs://"):
        cid = url[len("ipfs://"):]
        result = bridge({"op": "fetch-manifest", "cid": cid, "rpc": rpc_url(rpc)}, timeout)
        content = result["content"].encode("utf-8")
    else:
        validate_source_url(url)
        parts = urlsplit(url)
        if parts.scheme == "http" and not allow_local:
            raise ValueError("loopback manifest URLs require explicit --allow-local-sources")
        # Reuse the bounded DNS-pinned, redirect-checked HTTP transport. It sends
        # fixed headers and never inherits tokens, proxy or netrc credentials.
        hub = PublicHub(Path(tempfile.gettempdir()), base_url=f"{parts.scheme}://{parts.netloc}", timeout=timeout)
        try:
            with hub._response(url, time.monotonic() + timeout) as response:
                size = hub._content_length(response)
                if size is not None and size > MAX_MANIFEST_BYTES:
                    raise ValueError("manifest exceeds 16 MiB")
                content = response.read(MAX_MANIFEST_BYTES + 1)
        except UpstreamError as error:
            raise ValueError(str(error)) from error
    if len(content) > MAX_MANIFEST_BYTES or hashlib.sha256(content).hexdigest() != reference["sha256"]:
        raise ValueError("manifest does not match the signed SHA-256 or size limit")
    with tempfile.TemporaryDirectory(prefix="modelswarm-manifest-") as directory:
        path = Path(directory) / "manifest.json"
        path.write_bytes(content)
        manifest, digest = load_manifest(path, reference["sha256"])
    check_source_policy(manifest, allow_local)
    return manifest, digest


def resolve(value, *, rpc=None, timeout=120, allow_local=False):
    selector = parse_uri(value)
    result = bridge({"op": "resolve", "rpc": rpc_url(rpc), **selector}, timeout)
    release = result["release"]
    manifest, digest = manifest_from_reference(release["manifest"], rpc=rpc, timeout=timeout, allow_local=allow_local)
    if manifest["name"] != release["name"] or manifest["version"] != release["version"]:
        raise ValueError("manifest name/version differs from its signed announcement")
    return manifest, digest, {"signed": True, "publisher": result["publisher"], "release_cid": result["cid"],
                              "release_uri": release_uri(result["publisher"], release, result["cid"])}


def publish(args):
    manifest, digest = load_manifest(args.manifest)
    if args.manifest_url.startswith("ipfs://") and args.manifest.stat().st_size > MAX_IPFS_MANIFEST_BYTES:
        raise ValueError("IPFS manifests are limited to 1 MiB by the pinned PKC SDK; use an HTTPS manifest URL")
    rpc = rpc_url(args.rpc)
    private_key = read_key(args.key)
    # Fetch and validate before publishing a public pointer, including exact bytes.
    reference = {"url": args.manifest_url, "sha256": digest}
    remote, _ = manifest_from_reference(reference, rpc=rpc, timeout=args.rpc_timeout, allow_local=args.allow_local_sources)
    if remote != manifest:
        raise ValueError("manifest URL does not serve the input manifest")
    card = ""
    if args.card:
        with args.card.open("rb") as stream:
            raw = stream.read(24 * 1024 + 1)
        if len(raw) > 24 * 1024:
            raise ValueError("model card exceeds 24 KiB")
        card = raw.decode("utf-8")
    release = {"schema": "modelswarm/release/v0", "name": manifest["name"], "version": manifest["version"],
               "manifest": reference, "modelCard": card}
    result = bridge({"op": "publish", "rpc": rpc, "privateKey": private_key, "release": release}, args.rpc_timeout)
    return {"command": "publish", "signed": True, "publisher": result["publisher"], "release_cid": result["cid"],
            "release_uri": release_uri(result["publisher"], release, result["cid"]),
            "manifest_sha256": digest, "reused": result["reused"]}
