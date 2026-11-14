"""Verified blobs and snapshots in the Hugging Face on-disk cache layout.

Callers serialize writes for one manifest. A new snapshot appears atomically;
extending an existing snapshot adds complete files atomically, not as a group.
The cache is local user state, not a directory writable by an adversarial user.
"""

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile


_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}/[A-Za-z0-9][A-Za-z0-9_.-]{0,95}\Z")
_CHUNK = 4 * 1024 * 1024


def cache_root(value=None):
    """Resolve the selected cache's parent while preserving its root for validation."""
    selected = value if value is not None else os.environ.get("MODELSWARM_CACHE")
    if selected is None:
        selected = Path.home() / ".cache" / "modelswarm" / "hub"
    path = Path(selected).expanduser().absolute()
    parent = path.parent.resolve()
    return parent.parent if path.name == ".." else parent / path.name


def snapshot_revision(digest):
    if not isinstance(digest, str) or not _DIGEST.fullmatch(digest):
        raise ValueError("manifest digest must be 64 lowercase hexadecimal characters")
    # Hugging Face recognizes a 40-hex revision as an immutable cache snapshot.
    return digest[:40]


def _directories(path, create):
    path = Path(os.path.abspath(path))
    current = Path(path.anchor)
    for component in path.parts[1:]:
        current /= component
        try:
            info = current.lstat()
        except FileNotFoundError:
            if not create:
                raise
            try:
                current.mkdir(mode=0o700)
            except FileExistsError:
                pass
            info = current.lstat()
        if not stat.S_ISDIR(info.st_mode):
            raise ValueError(f"cache/source ancestor is not a real directory: {current}")
    return path


def ensure_directory(path):
    """Create directories while rejecting preexisting symlink/non-directory ancestors."""
    return _directories(path, create=True)


def _open_regular(path, *, single_link=False):
    path = Path(os.path.abspath(path))
    _directories(path.parent, create=False)
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or (single_link and before.st_nlink != 1):
        raise ValueError(f"expected a regular private file: {path}")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    info = os.fstat(descriptor)
    if (not stat.S_ISREG(info.st_mode) or (info.st_dev, info.st_ino) != (before.st_dev, before.st_ino)
            or (single_link and info.st_nlink != 1)):
        os.close(descriptor)
        raise ValueError(f"file changed while opening: {path}")
    return os.fdopen(descriptor, "rb")


def _verify_file(path, entry, *, single_link=False, output=None):
    digest, size = hashlib.sha256(), 0
    with _open_regular(path, single_link=single_link) as source:
        for block in iter(lambda: source.read(_CHUNK), b""):
            digest.update(block)
            size += len(block)
            if output is not None:
                output.write(block)
    if size != entry["size"] or digest.hexdigest() != entry["sha256"]:
        raise ValueError(f"cache/source file does not match manifest: {path}")


def _entries(manifest):
    name = manifest.get("name")
    if not isinstance(name, str) or not _NAME.fullmatch(name) or "--" in name or ".." in name:
        raise ValueError("manifest name must be a safe owner/model identifier")
    entries = {}
    for entry in manifest["files"]:
        relative = entry["path"]
        if not isinstance(relative, str):
            raise ValueError("snapshot paths must be strings")
        parts = PurePosixPath(relative).parts
        if (not relative or "\\" in relative or ":" in relative
                or relative.startswith("/") or any(p in (".", "..") for p in relative.split("/"))
                or "/".join(parts) != relative or any(ord(c) < 32 for c in relative)
                or relative in entries):
            raise ValueError(f"unsafe or duplicate snapshot path: {relative!r}")
        if not _DIGEST.fullmatch(entry["sha256"]) or type(entry["size"]) is not int or entry["size"] < 0:
            raise ValueError(f"invalid file digest or size: {relative}")
        entries[relative] = entry
    return name, entries


def _publish_blob(blobs, entry, source):
    blob = blobs / entry["sha256"]
    if os.path.lexists(blob):
        _verify_file(blob, entry)
        return blob
    descriptor, temporary_name = tempfile.mkstemp(prefix=".incoming-", dir=blobs)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            _verify_file(source, entry, output=output)
            output.flush()
            os.fsync(output.fileno())
        # Link with no replacement: another manifest may have just published it.
        try:
            os.link(temporary, blob, follow_symlinks=False)
        except FileExistsError:
            _verify_file(blob, entry)
    finally:
        temporary.unlink(missing_ok=True)
    return blob


def _check_snapshot(snapshot, blobs, entries, *, verify_payloads):
    existing = set()
    if not os.path.lexists(snapshot):
        return existing
    _directories(snapshot, create=False)
    expected_directories = {str(parent) for relative in entries
                            for parent in PurePosixPath(relative).parents if str(parent) != "."}

    def raise_walk_error(error):
        raise error

    for directory, children, files in os.walk(snapshot, onerror=raise_walk_error, followlinks=False):
        directory = Path(directory)
        for name in children:
            path = directory / name
            relative = path.relative_to(snapshot).as_posix()
            if path.is_symlink() or relative not in expected_directories:
                raise ValueError(f"unexpected snapshot directory: {path}")
        for name in files:
            path = directory / name
            relative = path.relative_to(snapshot).as_posix()
            if relative not in entries:
                raise ValueError(f"unexpected snapshot file: {path}")
            entry = entries[relative]
            blob = blobs / entry["sha256"]
            if not path.is_symlink() or os.readlink(path) != os.path.relpath(blob, path.parent):
                raise ValueError(f"snapshot file is not its expected blob link: {path}")
            if verify_payloads:
                _verify_file(blob, entry)
            elif not stat.S_ISREG(blob.lstat().st_mode):
                raise ValueError(f"expected a regular private file: {blob}")
            existing.add(relative)
    return existing


def _check_manifest_marker(directory, revision, digest, *, required=False):
    marker = directory / f"{revision}.json"
    expected = json.dumps({"manifest_sha256": digest}, sort_keys=True).encode() + b"\n"
    if not os.path.lexists(marker):
        if required:
            raise ValueError("existing snapshot is not owned by Modelswarm")
        return False
    with _open_regular(marker, single_link=True) as stream:
        if stream.read(len(expected) + 1) != expected:
            raise ValueError("cache revision belongs to another manifest")
    return True


def _manifest_marker(directory, revision, digest):
    if _check_manifest_marker(directory, revision, digest):
        return
    marker = directory / f"{revision}.json"
    expected = json.dumps({"manifest_sha256": digest}, sort_keys=True).encode() + b"\n"
    descriptor, temporary_name = tempfile.mkstemp(prefix=".incoming-", dir=directory)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(expected)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, marker, follow_symlinks=False)
        except FileExistsError:
            _check_manifest_marker(directory, revision, digest, required=True)
    finally:
        temporary.unlink(missing_ok=True)


def _read_snapshot(cache, manifest, digest, *, verify_payloads):
    revision = snapshot_revision(digest)
    name, entries = _entries(manifest)
    root = cache_root(cache)
    if not os.path.lexists(root):
        return None
    _directories(root, create=False)
    repository = root / ("models--" + name.replace("/", "--"))
    if not os.path.lexists(repository):
        return None
    _directories(repository, create=False)
    blobs, snapshots, metadata = (repository / part for part in ("blobs", "snapshots", ".modelswarm"))
    for directory in (blobs, snapshots, metadata):
        if os.path.lexists(directory):
            _directories(directory, create=False)
    snapshot = snapshots / revision
    published = os.path.lexists(snapshot)
    _check_manifest_marker(metadata, revision, digest, required=published)
    existing = _check_snapshot(snapshot, blobs, entries, verify_payloads=verify_payloads) if published else set()
    return snapshot, blobs, entries, existing


def cached_snapshot_file(cache, manifest, digest, relative):
    """Look up a published path in a structurally valid snapshot without reading blobs.

    The caller must verify the requested payload before serving it.
    """
    cached = _read_snapshot(cache, manifest, digest, verify_payloads=False)
    if cached is not None:
        snapshot, _, _, existing = cached
        if relative in existing:
            return snapshot / relative
    return None


def cached_files(cache, manifest, digest):
    """Return verified existing blobs, without creating cache directories or files.

    Existing snapshot links must be our exact links, with no foreign contents.
    The returned regular files have digest filenames; callers needing format
    inspection by suffix should copy them to private staging under the entry name.
    """
    cached = _read_snapshot(cache, manifest, digest, verify_payloads=True)
    if cached is None:
        return {}
    _, blobs, entries, _ = cached
    found = {}
    for relative, entry in entries.items():
        blob = blobs / entry["sha256"]
        if os.path.lexists(blob):
            _verify_file(blob, entry)
            found[relative] = blob
    return found


def materialize(cache, manifest, digest, verified):
    """Publish selected staged files; reject corrupt or foreign existing cache data.

    New snapshots are directory-atomic. Existing snapshots are extended only after
    every selected input/blob has verified, using atomic file links. Readers may
    briefly observe a verified subset during extension. No branch refs are set.
    """
    revision = snapshot_revision(digest)
    name, entries = _entries(manifest)
    if not verified or any(relative not in entries for relative in verified):
        raise ValueError("verified files must be a nonempty subset of the manifest")
    # Finish checking the entire selected set before changing visible snapshots.
    for relative, source in verified.items():
        _verify_file(source, entries[relative])
    root = ensure_directory(cache_root(cache))
    repository = ensure_directory(root / ("models--" + name.replace("/", "--")))
    blobs = ensure_directory(repository / "blobs")
    snapshots = ensure_directory(repository / "snapshots")
    metadata = ensure_directory(repository / ".modelswarm")
    snapshot = snapshots / revision
    _check_manifest_marker(metadata, revision, digest, required=os.path.lexists(snapshot))
    existing = _check_snapshot(snapshot, blobs, entries, verify_payloads=True)
    for relative, source in verified.items():
        _publish_blob(blobs, entries[relative], source)
    _manifest_marker(metadata, revision, digest)
    additions = sorted(set(verified) - existing)
    if not os.path.lexists(snapshot):
        temporary = Path(tempfile.mkdtemp(prefix=f".{revision}-", dir=snapshots))
        try:
            for relative in additions:
                link = temporary / relative
                ensure_directory(link.parent)
                link.symlink_to(os.path.relpath(blobs / entries[relative]["sha256"], link.parent))
            # Caller holds the per-manifest lock; reject even an empty foreign dir.
            if os.path.lexists(snapshot):
                raise ValueError(f"snapshot appeared during publication: {snapshot}")
            temporary.rename(snapshot)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
    else:
        for relative in additions:
            link = snapshot / relative
            ensure_directory(link.parent)
            # symlink() publishes a complete link and fails if a path exists.
            link.symlink_to(os.path.relpath(blobs / entries[relative]["sha256"], link.parent))
    return snapshot
