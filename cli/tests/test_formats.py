import json
from pathlib import Path
import pickle
import struct
import tempfile
import unittest

from modelswarm.formats import detect_format, is_flagged, is_flagged_path, validate_file_format


class FormatTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)

    def tearDown(self):
        self.directory.cleanup()

    def file(self, name, contents):
        path = self.root / name
        path.write_bytes(contents)
        return path

    def test_gguf_header_and_wrong_version(self):
        good = self.file("model.gguf", b"GGUF" + struct.pack("<IQQ", 3, 0, 0))
        self.assertEqual(detect_format(good), "gguf")
        self.assertFalse(is_flagged("gguf"))
        for contents in (b"GGUF", b"GGUF" + struct.pack("<IQQ", 99, 0, 0), b"not a model"):
            bad = self.file("bad.gguf", contents)
            self.assertEqual(detect_format(bad), "unknown")
            with self.assertRaisesRegex(ValueError, "format mismatch"):
                validate_file_format(bad, "gguf")

    def test_safetensors_offsets_and_header_length(self):
        header = {"tensor": {"dtype": "F32", "shape": [1], "data_offsets": [0, 4]}}
        encoded = json.dumps(header).encode().ljust(128, b" ")
        path = self.file("model.safetensors", struct.pack("<Q", len(encoded)) + encoded + b"\0" * 4)
        self.assertEqual(detect_format(path), "safetensors")
        # A 128-byte safetensors header starts with 0x80; it is not pickle.
        self.assertFalse(is_flagged(detect_format(path)))
        header["tensor"]["data_offsets"] = [1, 4]
        encoded = json.dumps(header).encode()
        path.write_bytes(struct.pack("<Q", len(encoded)) + encoded + b"\0" * 4)
        self.assertEqual(detect_format(path), "unknown")

    def test_safetensors_rejects_duplicate_header_and_trailing_data(self):
        for encoded, data in ((b'{"x":{},"x":{}}', b""), (b"{}", b"unindexed")):
            path = self.file("bad.safetensors", struct.pack("<Q", len(encoded)) + encoded + data)
            self.assertEqual(detect_format(path), "unknown")

    def test_safetensors_rejects_unknown_dtype_and_inconsistent_shape(self):
        for dtype, shape in (("EXEC", [1]), ("F32", [9]), ("F4", [1])):
            header = {"x": {"dtype": dtype, "shape": shape, "data_offsets": [0, 4]}}
            encoded = json.dumps(header).encode()
            path = self.file("shape.safetensors", struct.pack("<Q", len(encoded)) + encoded + b"\0" * 4)
            self.assertEqual(detect_format(path), "unknown")

    def test_pickle_and_code_are_flagged_even_with_safe_extensions(self):
        for name, contents, expected in (("fake.gguf", pickle.dumps({"a": 1}, protocol=4), "pickle"),
                                         ("config.json", b"PK\x03\x04archive", "pickle"),
                                         ("readme.txt", b"#!/usr/bin/python\nprint('x')", "code"),
                                         ("loader.py", b"GGUF" + struct.pack("<IQQ", 3, 0, 0), "code"),
                                         ("weights.bin", b"opaque", "pickle")):
            with self.subTest(name=name):
                self.assertEqual(detect_format(self.file(name, contents)), expected)
                self.assertTrue(is_flagged(expected))

    def test_json_text_and_empty_file(self):
        self.assertEqual(detect_format(self.file("config.json", b'{"model_type":"qwen2"}')), "json")
        self.assertEqual(detect_format(self.file("README.md", "café\n".encode())), "text")
        self.assertEqual(detect_format(self.file("LICENSE", b"Apache-2.0\n")), "text")
        self.assertEqual(detect_format(self.file("empty.txt", b"")), "text")
        self.assertEqual(detect_format(self.file("empty.json", b"")), "unknown")
        self.assertEqual(detect_format(self.file("invalid.txt", b"binary\0data")), "unknown")
        self.assertEqual(detect_format(self.file("duplicate.json", b'{"a":1,"a":2}')), "unknown")

    def test_path_risk_does_not_trust_declared_format_or_need_a_file(self):
        for path in ("nested/modeling.py", "WEIGHTS.BIN", "model.ckpt", "chat_template.jinja", "tools/run.SH"):
            with self.subTest(path=path):
                self.assertTrue(is_flagged_path(path))
        for path in ("config.json", "weights.safetensors", "model.gguf", "README.md"):
            with self.subTest(path=path):
                self.assertFalse(is_flagged_path(path))


if __name__ == "__main__":
    unittest.main()
