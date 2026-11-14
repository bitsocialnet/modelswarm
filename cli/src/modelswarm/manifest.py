"""Portable, unsigned Modelswarm manifest v0 and its bounded transport metadata."""

import base64
import binascii
import hashlib
import json
from pathlib import Path
import re
import unicodedata
from urllib.parse import unquote, urlsplit

import libtorrent as lt

from .formats import FORMATS


SCHEMA = "modelswarm/manifest/v0"
MAX_MANIFEST_BYTES = 16 * 1024 * 1024
MAX_FILES = 4096
MAX_FILE_BYTES = 1 << 40
MAX_TOTAL_BYTES = 4 << 40
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
HEX256 = re.compile(r"[0-9a-f]{64}\Z")
NAME_PART = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._-]{0,94}[A-Za-z0-9])?\Z")
VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
RESERVED = re.compile(r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?\Z", re.I)


def _keys(value, required, label):
    if not isinstance(value, dict) or set(value) != set(required):
        names = [key.decode("utf-8") if isinstance(key, bytes) else key for key in sorted(required)]
        raise ValueError(f"{label} must contain exactly: {', '.join(names)}")


def _digest(value, label):
    if not isinstance(value, str) or not HEX256.fullmatch(value):
        raise ValueError(f"{label} must be a lowercase SHA-256 hex digest")


def _integer(value, minimum, maximum, label):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{label} must be an integer between {minimum} and {maximum}")


def _no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def validate_relative_path(path):
    """Reject paths that cannot safely coexist on supported desktop filesystems."""
    if not isinstance(path, str) or not path or len(path.encode("utf-8", errors="surrogatepass")) > 1024:
        raise ValueError("file path must be a nonempty relative path of at most 1024 bytes")
    if "\\" in path or any(unicodedata.category(char) in ("Cc", "Cf", "Cs") for char in path):
        raise ValueError(f"file path contains a backslash or control character: {path!r}")
    parts = path.split("/")
    if len(parts) > 32:
        raise ValueError("file path is too deeply nested")
    for part in parts:
        if (not part or part in (".", "..") or part.endswith((".", " "))
                or len(part.encode("utf-8")) > 255 or any(char in '<>:"|?*' for char in part)
                or RESERVED.fullmatch(part)
                or part.casefold() in {".git", ".hg", ".svn", ".modelswarm", ".pad"}):
            raise ValueError(f"unsafe or nonportable file path: {path!r}")
    return path


def _path_key(path):
    return unicodedata.normalize("NFC", path).casefold()


def validate_source_url(url):
    if not isinstance(url, str) or not url or len(url) > 8192:
        raise ValueError("HTTP source URL must be a nonempty string of at most 8192 characters")
    if "\\" in url or any(unicodedata.category(char) in ("Cc", "Cf", "Cs") for char in url):
        raise ValueError("HTTP source URL contains invalid characters")
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as error:
        raise ValueError("malformed HTTP source URL") from error
    if (parts.scheme not in ("http", "https") or not parts.hostname or not parts.path
            or parts.username is not None or parts.password is not None or parts.fragment
            or (port is not None and not 1 <= port <= 65535)):
        raise ValueError("source must be an HTTP(S) file URL without credentials or a fragment")
    return url


def torrent_bytes(entry):
    """Decode already-validated nonempty-file metadata, with a size bound."""
    torrent = entry.get("torrent")
    if not isinstance(torrent, dict):
        raise ValueError("nonempty file needs torrent metadata")
    metadata = torrent.get("metadata")
    if not isinstance(metadata, str) or len(metadata) > MAX_MANIFEST_BYTES:
        raise ValueError("embedded torrent is missing or too large")
    try:
        return base64.b64decode(metadata, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError("torrent metadata is not valid base64") from error


def _validate_torrent(entry):
    _keys(entry["torrent"], {"infohash_v2", "metadata"}, "torrent")
    _digest(entry["torrent"]["infohash_v2"], "torrent infohash_v2")
    encoded = torrent_bytes(entry)
    try:
        decoded = lt.bdecode(encoded)
        if not isinstance(decoded, dict) or lt.bencode(decoded) != encoded:
            raise ValueError("torrent metadata must use canonical bencoding")
        # Sources come only from the explicit manifest list. Unknown torrent
        # fields cannot smuggle trackers, web seeds, peers, nodes or signatures.
        _keys(decoded, {b"info", b"piece layers"}, "torrent metadata")
        info = decoded[b"info"]
        _keys(info, {b"file tree", b"meta version", b"name", b"piece length"}, "torrent info")
        basename = entry["path"].rsplit("/", 1)[-1]
        name_bytes = basename.encode("utf-8")
        if info[b"meta version"] != 2 or info[b"name"] != name_bytes:
            raise ValueError("torrent version or name does not match the manifest")
        piece_length = info[b"piece length"]
        _integer(piece_length, 16 * 1024, 16 * 1024 * 1024, "piece length")
        if piece_length & (piece_length - 1):
            raise ValueError("piece length must be a power of two")
        expected_tree = {name_bytes: {b"": {b"length": entry["size"], b"pieces root": bytes.fromhex(entry["pieces_root"])}}}
        if info[b"file tree"] != expected_tree:
            raise ValueError("torrent file tree does not match the manifest file, size and root")
        digest = hashlib.sha256(lt.bencode(info)).hexdigest()
        if digest != entry["torrent"]["infohash_v2"]:
            raise ValueError("torrent infohash does not match the manifest")
        piece_count = (entry["size"] + piece_length - 1) // piece_length
        layers = decoded[b"piece layers"]
        expected_roots = {bytes.fromhex(entry["pieces_root"])} if piece_count > 1 else set()
        if not isinstance(layers, dict) or set(layers) != expected_roots:
            raise ValueError("torrent must contain exactly the required piece layer")
        if expected_roots:
            layer = layers[next(iter(expected_roots))]
            if not isinstance(layer, bytes) or len(layer) != piece_count * 32:
                raise ValueError("torrent piece layer has the wrong length")
        parsed = lt.torrent_info(encoded)  # Also authenticates the layer against its root.
        storage = parsed.files()
        if not parsed.info_hashes().has_v2() or parsed.info_hashes().has_v1():
            raise ValueError("manifest v0 requires a v2-only torrent")
        if (storage.file_path(0) != basename or storage.file_size(0) != entry["size"]
                or storage.file_offset(0) != 0 or int(storage.file_flags(0)) != 0):
            raise ValueError("torrent data file is not an ordinary matching file")
        padding = (-entry["size"]) % piece_length
        if storage.num_files() != (2 if padding else 1):
            raise ValueError("torrent contains extra files")
        if padding and any(unquote(urlsplit(source["url"]).path.rsplit("/", 1)[-1]) != basename
                           for source in entry["sources"]):
            raise ValueError("payload source URL must end with the model file name for a padded torrent")
        if padding and (storage.file_path(1) != f"{basename}/.pad/{padding}"
                        or storage.file_size(1) != padding or storage.file_offset(1) != entry["size"]
                        or int(storage.file_flags(1)) != int(lt.file_storage.flag_pad_file)):
            raise ValueError("torrent contains unexpected padding")
        if str(storage.root(0)) != entry["pieces_root"] or parsed.num_pieces() != piece_count:
            raise ValueError("torrent root or piece count does not match the manifest")
    except (RuntimeError, KeyError, TypeError, OverflowError) as error:
        raise ValueError(f"invalid embedded torrent: {error}") from error


def validate_manifest(value):
    _keys(value, {"schema", "name", "version", "license", "files"}, "manifest")
    if value["schema"] != SCHEMA:
        raise ValueError(f"unsupported manifest schema; expected {SCHEMA}")
    name = value["name"]
    if (not isinstance(name, str) or len(name.split("/")) != 2
            or any(not NAME_PART.fullmatch(part) or ".." in part or "--" in part for part in name.split("/"))):
        raise ValueError("manifest name must be an owner/model identifier")
    if not isinstance(value["version"], str) or not VERSION.fullmatch(value["version"]):
        raise ValueError("manifest version must be a short alphanumeric label with dots, underscores or hyphens")
    license_name = value["license"]
    if (not isinstance(license_name, str) or not license_name.strip() or len(license_name) > 128
            or any(unicodedata.category(char) in ("Cc", "Cf", "Cs") for char in license_name)):
        raise ValueError("manifest license must be a nonempty short label")
    entries = value["files"]
    if not isinstance(entries, list) or not 1 <= len(entries) <= MAX_FILES:
        raise ValueError(f"manifest must contain between 1 and {MAX_FILES} files")
    paths = set()
    directories = {}
    total = 0
    for entry in entries:
        _keys(entry, {"path", "size", "sha256", "pieces_root", "format", "torrent", "sources"}, "file")
        path = validate_relative_path(entry["path"])
        key = _path_key(path)
        if key in paths:
            raise ValueError(f"duplicate or case/Unicode-colliding file path: {path}")
        paths.add(key)
        # Distinct leaf names can still alias a shared directory on APFS/NTFS.
        parts = path.split("/")
        for depth in range(1, len(parts)):
            directory = "/".join(parts[:depth])
            directory_key = _path_key(directory)
            if directories.setdefault(directory_key, directory) != directory:
                raise ValueError(f"case/Unicode-colliding directory path: {directory}")
        _integer(entry["size"], 0, MAX_FILE_BYTES, "file size")
        total += entry["size"]
        if total > MAX_TOTAL_BYTES:
            raise ValueError("manifest total file size exceeds 4 TiB")
        _digest(entry["sha256"], "file sha256")
        if not isinstance(entry["format"], str) or entry["format"] not in FORMATS:
            raise ValueError("unrecognized file format")
        sources = entry["sources"]
        if not isinstance(sources, list) or len(sources) > 16:
            raise ValueError("file must have a list of at most 16 HTTP sources")
        for source in sources:
            _keys(source, {"type", "url"}, "source")
            if source["type"] != "http":
                raise ValueError("manifest v0 supports only explicit HTTP sources")
            validate_source_url(source["url"])
            if "?" in source["url"]:
                raise ValueError("payload source URLs cannot contain query parameters; use a direct file URL")
        if entry["size"] == 0:
            if (entry["pieces_root"] is not None or entry["torrent"] is not None
                    or entry["sha256"] != EMPTY_SHA256 or sources):
                raise ValueError("empty files need the empty SHA-256, null root/torrent, and no sources")
        else:
            _digest(entry["pieces_root"], "file pieces_root")
            _validate_torrent(entry)
    for path in paths:
        parts = path.split("/")
        if any("/".join(parts[:i]) in paths for i in range(1, len(parts))):
            raise ValueError("file path collides with another file's parent directory")
    if len(encode_manifest(value)) > MAX_MANIFEST_BYTES:
        raise ValueError("manifest exceeds the 16 MiB limit")
    return value


def encode_manifest(manifest):
    """Canonical representation for make; callers validate the resulting value."""
    try:
        return (json.dumps(manifest, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as error:
        raise ValueError(f"manifest cannot be encoded: {error}") from error


def load_manifest(path, expected_sha256=None):
    with Path(path).open("rb") as stream:
        encoded = stream.read(MAX_MANIFEST_BYTES + 1)
    if len(encoded) > MAX_MANIFEST_BYTES:
        raise ValueError("manifest exceeds the 16 MiB limit")
    digest = hashlib.sha256(encoded).hexdigest()
    if expected_sha256 is not None:
        _digest(expected_sha256, "expected manifest SHA-256")
        if digest != expected_sha256:
            raise ValueError("manifest does not match the expected SHA-256")
    try:
        value = json.loads(encoded, object_pairs_hook=_no_duplicates,
                           parse_constant=lambda constant: (_ for _ in ()).throw(ValueError(f"invalid JSON constant: {constant}")))
    except (json.JSONDecodeError, UnicodeError, RecursionError) as error:
        raise ValueError(f"invalid manifest JSON: {error}") from error
    return validate_manifest(value), digest
