"""Noninteractive Modelswarm make/verify/pull commands; results are JSON."""

import argparse
from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import shutil
import stat
import sys
import tempfile
import threading
from urllib.parse import quote, urlsplit, urlunsplit

from . import __version__
from .cache import cache_root, cached_files, ensure_directory, materialize, snapshot_revision
from .engine import InterruptedDownload, MIB, check_file, describe_file, download_file, peer_address
from .formats import detect_format, is_flagged, is_flagged_path
from .manifest import MAX_FILES, SCHEMA, encode_manifest, load_manifest, validate_manifest, validate_relative_path, validate_source_url


def progress(event, **fields):
    print(json.dumps({"event": event, **fields}), file=sys.stderr, flush=True)


def write_new(path, data):
    """Publish a complete manifest without replacing a preexisting file."""
    if not path.parent.is_dir():
        raise ValueError("manifest output parent directory does not exist")
    descriptor, temporary = tempfile.mkstemp(prefix=".modelswarm-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
    finally:
        os.unlink(temporary)


def make(args):
    if args.directory.is_symlink():
        raise ValueError("source directory must not be a symlink")
    directory = args.directory.resolve(strict=True)
    if not directory.is_dir():
        raise ValueError("make requires a directory")
    output = args.output.absolute()
    if output.resolve().is_relative_to(directory):
        raise ValueError("write the manifest outside the input directory")
    if output.exists() or output.is_symlink():
        raise ValueError("manifest output already exists; choose a new path")
    if args.piece_size < 16384 or args.piece_size > 16 * MIB or args.piece_size & (args.piece_size - 1):
        raise ValueError("piece size must be a power of two between 16 KiB and 16 MiB")
    bases = [validate_source_url(url) for url in args.http_base]
    paths = []
    for root, directories, files in os.walk(directory, followlinks=False):
        for name in directories + files:
            path = Path(root) / name
            if path.is_symlink():
                raise ValueError(f"source symlinks are not supported: {path.relative_to(directory)}")
        for name in files:
            path = Path(root) / name
            if not stat.S_ISREG(path.stat().st_mode):
                raise ValueError(f"source is not a regular file: {path.relative_to(directory)}")
            relative = validate_relative_path(path.relative_to(directory).as_posix())
            paths.append((relative, path))
            if len(paths) > MAX_FILES:
                raise ValueError(f"at most {MAX_FILES} files are allowed")
    if not paths:
        raise ValueError("source directory contains no files")
    entries = []
    for relative, path in sorted(paths):
        sources = []
        for base in bases:
            parts = urlsplit(base)
            url = urlunsplit(parts._replace(path=parts.path.rstrip("/") + "/" + quote(relative, safe="/")))
            sources.append({"type": "http", "url": url})
        entry = describe_file(path, relative, detect_format(path), sources, args.piece_size)
        entries.append(entry)
        progress("file_hashed", path=relative, size=entry["size"], format=entry["format"])
    manifest = {"schema": SCHEMA, "name": args.name, "version": args.version,
                "license": args.license, "files": entries}
    validate_manifest(manifest)
    encoded = encode_manifest(manifest)
    write_new(output, encoded)
    return {"command": "make", "manifest": str(output), "manifest_sha256": hashlib.sha256(encoded).hexdigest(),
            "files": len(entries), "bytes": sum(entry["size"] for entry in entries),
            "flagged": [entry["path"] for entry in entries if is_flagged(entry["format"])], "signed": False}


def select(manifest, requested):
    known = {entry["path"] for entry in manifest["files"]}
    missing = set(requested) - known
    if missing:
        raise ValueError(f"files not in manifest: {', '.join(sorted(missing))}")
    return [entry for entry in manifest["files"] if not requested or entry["path"] in requested]


def verify(args):
    manifest, digest = load_manifest(args.manifest, args.manifest_sha256)
    directory = args.directory.resolve(strict=True)
    if not directory.is_dir():
        raise ValueError("verify requires a directory")
    checked, errors = [], []
    for entry in select(manifest, args.file):
        try:
            # Following ordinary cache links is necessary for HF snapshots.
            # This command only reads; it never loads model code or writes files.
            check_file(entry, directory / entry["path"])
            checked.append(entry["path"])
        except (OSError, ValueError, RuntimeError) as error:
            errors.append({"path": entry["path"], "error": str(error)})
    return {"command": "verify", "manifest_sha256": digest, "verified": checked, "errors": errors, "signed": False}


@contextmanager
def release_lock(directory, digest):
    lock = directory / f"{digest}.lock"
    if lock.is_symlink():
        raise ValueError("symlink lock is not allowed")
    descriptor = os.open(lock, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode) or os.fstat(descriptor).st_nlink != 1:
            raise ValueError("invalid lock file")
        try:
            if os.name == "nt":
                import msvcrt
                if os.fstat(descriptor).st_size == 0:
                    os.write(descriptor, b"0")
                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise ValueError("another pull is using this manifest and cache") from error
        yield
    finally:
        os.close(descriptor)


def pull(args):
    manifest, digest = load_manifest(args.manifest, args.manifest_sha256)
    entries = select(manifest, args.file)
    flagged = [entry["path"] for entry in entries if is_flagged(entry["format"]) or is_flagged_path(entry["path"])]
    if flagged and args.file and not args.allow_unsafe:
        raise ValueError(f"flagged files require --allow-unsafe: {', '.join(flagged)}")
    skipped = [] if args.allow_unsafe else flagged
    if not args.allow_unsafe:
        entries = [entry for entry in entries if entry["path"] not in flagged]
    if not entries:
        raise ValueError("no unflagged files selected; review the manifest before using --allow-unsafe")
    if not math.isfinite(args.timeout) or args.timeout <= 0 or not 0 <= args.rate_limit <= 2**31 - 1:
        raise ValueError("timeout must be finite and positive; rate limit must be between 0 and 2147483647")
    if not math.isfinite(args.checkpoint_interval) or args.checkpoint_interval < 1:
        raise ValueError("checkpoint interval must be finite and at least one second")
    peers = [peer_address(value) for value in args.peer]
    root = ensure_directory(cache_root(args.cache_dir))
    state = ensure_directory(root / ".modelswarm")
    cancel = threading.Event()
    original_handlers = {}
    for signum in (signal.SIGINT, signal.SIGTERM):
        original_handlers[signum] = signal.signal(signum, lambda *_: cancel.set())
    try:
        with release_lock(state, digest):
            working = ensure_directory(state / digest / "files")
            cached = cached_files(root, manifest, digest)
            verified = {}
            for entry in entries:
                if cancel.is_set():
                    raise InterruptedDownload("interrupted; verified files and partial data retained")
                file_id = hashlib.sha256(entry["path"].encode("utf-8")).hexdigest()
                directory = ensure_directory(working / file_id)
                if entry["path"] in cached:
                    # Keep the original basename for format inspection; hashed
                    # blob names lose suffix-based code/pickle detection.
                    payload = ensure_directory(directory / "payload") / Path(entry["path"]).name
                    if payload.is_symlink() or (payload.exists() and (not payload.is_file() or payload.stat().st_nlink != 1)):
                        raise ValueError("unsafe staged payload path")
                    shutil.copyfile(cached[entry["path"]], payload)
                    check_file(entry, payload)
                    verified[entry["path"]] = cached[entry["path"]]
                    progress("file_cached", path=entry["path"])
                    continue
                verified[entry["path"]] = download_file(entry, directory, peers=peers,
                    discovery=not args.no_discovery, timeout=args.timeout, rate=args.rate_limit,
                    checkpoint_interval=args.checkpoint_interval, cancel=cancel, emit=progress)
            if cancel.is_set():
                raise InterruptedDownload("interrupted before cache publication; verified data retained")
            snapshot = materialize(root, manifest, digest, verified)
            return {"command": "pull", "name": manifest["name"], "manifest_sha256": digest,
                    "revision": snapshot_revision(digest), "cache_dir": str(root), "snapshot": str(snapshot),
                    "files": [entry["path"] for entry in entries], "skipped_flagged": skipped, "signed": False}
    finally:
        for signum, handler in original_handlers.items():
            signal.signal(signum, handler)


def parser():
    result = argparse.ArgumentParser(prog="modelswarm", description="Experimental model releases over BitTorrent v2 and HTTP")
    result.add_argument("--version", action="version", version=__version__)
    commands = result.add_subparsers(dest="command", required=True)
    command = commands.add_parser("make", help="hash a directory and create a portable manifest")
    command.add_argument("directory", type=Path)
    command.add_argument("--output", "-o", type=Path, required=True)
    command.add_argument("--name", required=True, help="owner/model")
    command.add_argument("--version", default="v0")
    command.add_argument("--license", required=True)
    command.add_argument("--http-base", action="append", default=[], help="HTTP(S) directory containing the release files")
    command.add_argument("--piece-size", type=int, default=MIB)
    command.set_defaults(function=make)
    for name, function in (("verify", verify), ("pull", pull)):
        command = commands.add_parser(name, help="verify local files" if name == "verify" else "download a manifest into the model cache")
        command.add_argument("manifest", type=Path)
        command.add_argument("--manifest-sha256", help="optional out-of-band digest of the manifest bytes")
        command.add_argument("--file", action="append", default=[], help="select an exact manifest path; repeat for several files")
        command.set_defaults(function=function)
        if name == "verify":
            command.add_argument("directory", type=Path)
        else:
            command.add_argument("--cache-dir", type=Path)
            command.add_argument("--allow-unsafe", action="store_true", help="explicitly include code, pickle and unknown formats; never execute them")
            command.add_argument("--peer", action="append", default=[], help="explicit peer host:port or [IPv6]:port")
            command.add_argument("--no-discovery", action="store_true", help="disable DHT; use only explicit peers and HTTP sources")
            command.add_argument("--timeout", type=float, default=300, help="seconds per file before saving progress and failing")
            command.add_argument("--rate-limit", type=int, default=0, help="download bytes/s; zero means unlimited")
            command.add_argument("--checkpoint-interval", type=float, default=15, help="seconds between flushed resume checkpoints; minimum one")
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        result = args.function(args)
        result["ok"] = not result.get("errors")
        print(json.dumps(result, sort_keys=True), flush=True)
        return 0 if result["ok"] else 1
    except InterruptedDownload as error:
        print(json.dumps({"ok": False, "error": str(error)}), flush=True)
        return 130
    except (OSError, ValueError, RuntimeError, TimeoutError) as error:
        print(json.dumps({"ok": False, "error": str(error)}), flush=True)
        return 1
