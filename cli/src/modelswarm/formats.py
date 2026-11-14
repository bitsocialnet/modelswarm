"""Conservative format inspection; no deserialization or execution of model code."""

import codecs
import json
import math
from pathlib import Path
import struct


FORMATS = frozenset({"gguf", "safetensors", "json", "text", "code", "pickle", "unknown"})
FLAGGED_FORMATS = frozenset({"code", "pickle", "unknown"})
MAX_HEADER_BYTES = 16 * 1024 * 1024
MAX_JSON_BYTES = 128 * 1024 * 1024
CODE_SUFFIXES = {".py", ".pyc", ".pyo", ".ipynb", ".sh", ".bash", ".zsh", ".js", ".mjs", ".cjs", ".ts", ".ps1", ".bat", ".cmd", ".exe", ".dll", ".so", ".dylib", ".jinja", ".jinja2"}
PICKLE_SUFFIXES = {".bin", ".pt", ".pth", ".ckpt", ".pkl", ".pickle", ".joblib"}
TEXT_SUFFIXES = {".txt", ".md", ".rst", ".csv", ".tsv", ".yaml", ".yml", ".toml", ".ini", ".cfg"}
TEXT_NAMES = {"license", "licence", "notice", "readme", ".gitattributes", ".gitignore"}
# safetensors/src/tensor.rs Dtype::bitsize; unknown future dtypes stay flagged.
DTYPE_BITS = {
    "F4": 4, "F6_E2M3": 6, "F6_E3M2": 6,
    "BOOL": 8, "U8": 8, "I8": 8, "F8_E5M2": 8, "F8_E4M3": 8,
    "F8_E8M0": 8, "F8_E4M3FNUZ": 8, "F8_E5M2FNUZ": 8,
    "I16": 16, "U16": 16, "F16": 16, "BF16": 16,
    "I32": 32, "U32": 32, "F32": 32,
    "C64": 64, "F64": 64, "I64": 64, "U64": 64,
}


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _json(data):
    return json.loads(data, object_pairs_hook=_unique_keys,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"invalid JSON constant: {value}")))


def _safetensors(path, size):
    with path.open("rb") as stream:
        prefix = stream.read(8)
        if len(prefix) != 8:
            return False
        length = int.from_bytes(prefix, "little")
        if not 2 <= length <= min(MAX_HEADER_BYTES, size - 8):
            return False
        header_bytes = stream.read(length)
    if not header_bytes.startswith(b"{"):
        return False
    try:
        header = _json(header_bytes)
    except (ValueError, UnicodeError, RecursionError):
        return False
    if not isinstance(header, dict):
        return False
    data_size = size - 8 - length
    intervals = []
    for name, tensor in header.items():
        if name == "__metadata__":
            if not isinstance(tensor, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in tensor.items()):
                return False
            continue
        if not isinstance(tensor, dict) or set(tensor) != {"dtype", "shape", "data_offsets"}:
            return False
        if not isinstance(tensor["dtype"], str) or tensor["dtype"] not in DTYPE_BITS:
            return False
        shape, offsets = tensor["shape"], tensor["data_offsets"]
        if (not isinstance(shape, list) or len(shape) > 32
                or any(type(dimension) is not int or not 0 <= dimension < (1 << 63) for dimension in shape)):
            return False
        if (not isinstance(offsets, list) or len(offsets) != 2
                or any(type(offset) is not int for offset in offsets)
                or not 0 <= offsets[0] <= offsets[1] <= data_size):
            return False
        bits = math.prod(shape) * DTYPE_BITS[tensor["dtype"]]
        if bits % 8 or bits // 8 != offsets[1] - offsets[0]:
            return False
        intervals.append(tuple(offsets))
    cursor = 0
    for start, end in sorted(intervals):
        if start != cursor:
            return False
        cursor = end
    return cursor == data_size


def _text(path):
    decoder = codecs.getincrementaldecoder("utf-8")("strict")
    try:
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                text = decoder.decode(block)
                if any(ord(char) < 32 and char not in "\t\r\n\f" for char in text):
                    return False
            decoder.decode(b"", final=True)
    except UnicodeError:
        return False
    return True


def detect_format(path):
    path = Path(path)
    size = path.stat().st_size
    with path.open("rb") as stream:
        prefix = stream.read(64)
    suffix = path.suffix.casefold()
    # Filename risk takes priority over a forged data-only magic prefix.
    if suffix in CODE_SUFFIXES:
        return "code"
    # A little-endian safetensors length can start with pickle or code magic.
    if (suffix != ".gguf" and suffix not in PICKLE_SUFFIXES
            and prefix[8:9] == b"{" and _safetensors(path, size)):
        return "safetensors"
    if prefix.startswith((b"#!", b"\x7fELF", b"MZ")):
        return "code"
    pickle_magic = len(prefix) >= 2 and prefix[0] == 0x80 and 2 <= prefix[1] <= 5
    if suffix in PICKLE_SUFFIXES or pickle_magic or prefix.startswith(b"PK\x03\x04"):
        return "pickle"
    if prefix.startswith(b"GGUF"):
        if len(prefix) >= 24 and struct.unpack("<I", prefix[4:8])[0] in (2, 3):
            return "gguf"
        return "unknown"
    if suffix == ".gguf":
        return "unknown"
    if suffix == ".safetensors":
        return "unknown"
    if suffix == ".json":
        if size > MAX_JSON_BYTES:
            return "unknown"
        try:
            _json(path.read_bytes())
            return "json"
        except (ValueError, UnicodeError, RecursionError):
            return "unknown"
    if suffix in TEXT_SUFFIXES or path.name.casefold() in TEXT_NAMES:
        return "text" if _text(path) else "unknown"
    return "unknown"


def is_flagged(format_name):
    if format_name not in FORMATS:
        raise ValueError(f"unrecognized format: {format_name}")
    return format_name in FLAGGED_FORMATS


def is_flagged_path(path):
    """Apply filename risk before downloading, independent of a claimed format."""
    suffix = Path(path).suffix.casefold()
    return suffix in CODE_SUFFIXES or suffix in PICKLE_SUFFIXES


def validate_file_format(path, declared):
    if declared not in FORMATS:
        raise ValueError(f"unrecognized declared format: {declared}")
    detected = detect_format(path)
    if detected != declared:
        raise ValueError(f"format mismatch for {Path(path).name}: declared {declared}, detected {detected}")
