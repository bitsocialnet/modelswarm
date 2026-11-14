import base64
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import libtorrent as lt

from modelswarm.engine import describe_file
from modelswarm.manifest import (
    EMPTY_SHA256, MAX_MANIFEST_BYTES, SCHEMA, encode_manifest, load_manifest,
    validate_manifest, validate_relative_path, validate_source_url,
)


class ManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.root = Path(cls.directory.name)
        source = cls.root / "weights.gguf"
        source.write_bytes(b"GGUF\x03\x00\x00\x00" + b"\x00" * (32 * 1024 + 117))
        storage = lt.file_storage()
        storage.add_file(source.name, source.stat().st_size)
        torrent = lt.create_torrent(storage, 16 * 1024, flags=lt.create_torrent.v2_only)
        lt.set_piece_hashes(torrent, str(cls.root))
        generated = torrent.generate()
        cls.torrent = {key: generated[key] for key in (b"info", b"piece layers")}
        encoded = lt.bencode(cls.torrent)
        info = lt.torrent_info(encoded)
        cls.entry = {
            "path": "nested/weights.gguf", "size": source.stat().st_size,
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "pieces_root": str(info.files().root(0)), "format": "gguf",
            "torrent": {"infohash_v2": str(info.info_hashes().v2), "metadata": base64.b64encode(encoded).decode()},
            "sources": [{"type": "http", "url": "http://127.0.0.1:12345/nested/weights.gguf"}],
        }

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def manifest(self):
        return {"schema": SCHEMA, "name": "example/model", "version": "v1.0", "license": "apache-2.0", "files": [copy.deepcopy(self.entry)]}

    def empty(self, path="empty.txt"):
        return {"path": path, "size": 0, "sha256": EMPTY_SHA256, "pieces_root": None,
                "format": "text", "torrent": None, "sources": []}

    def test_round_trip_and_expected_digest(self):
        manifest = self.manifest()
        encoded = encode_manifest(manifest)
        self.assertEqual(encode_manifest(dict(reversed(list(manifest.items())))), encoded)
        path = self.root / "round-trip.json"
        path.write_bytes(encoded)
        value, digest = load_manifest(path, hashlib.sha256(encoded).hexdigest())
        self.assertEqual(value, manifest)
        self.assertEqual(digest, hashlib.sha256(encoded).hexdigest())
        with self.assertRaisesRegex(ValueError, "expected SHA-256"):
            load_manifest(path, "0" * 64)

    def test_empty_file_has_no_transport(self):
        manifest = self.manifest()
        manifest["files"].append(self.empty())
        self.assertEqual(validate_manifest(manifest), manifest)
        manifest["files"][-1]["sources"] = self.entry["sources"]
        with self.assertRaisesRegex(ValueError, "empty files"):
            validate_manifest(manifest)

    def test_reject_nonportable_paths(self):
        for path in ("/absolute", "../escape", "a/../escape", "a//b", "a\\b", "C:thing", "NUL", "con.txt", "a/COM1", "a.", "a ", ".git/config", "a\x00b", "a\u202eb", "a/.pad/z"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                validate_relative_path(path)

    def test_reject_collisions(self):
        for first, second in (("same.txt", "same.txt"), ("A.txt", "a.txt"), ("café.txt", "cafe\u0301.txt"), ("dir", "DIR/child.txt")):
            manifest = self.manifest()
            manifest["files"] = [self.empty(first), self.empty(second)]
            with self.subTest(paths=(first, second)), self.assertRaises(ValueError):
                validate_manifest(manifest)

    def test_reject_directory_aliases_before_cache_creation(self):
        pairs = (("Dir/a.txt", "dir/b.txt"), ("café/a.txt", "cafe\u0301/b.txt"),
                 ("nested/Dir/a.txt", "nested/dir/deeper/b.txt"))
        for pair in pairs:
            for paths in (pair, tuple(reversed(pair))):
                with self.subTest(paths=paths), tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary).resolve()
                    manifest = self.manifest()
                    manifest["files"] = [self.empty(path) for path in paths]
                    with self.assertRaisesRegex(ValueError, "colliding directory"):
                        validate_manifest(manifest)
                    path = root / "release.json"
                    path.write_bytes(encode_manifest(manifest))
                    cache = root / "cache"
                    result = subprocess.run(
                        [sys.executable, "-m", "modelswarm", "pull", str(path),
                         "--cache-dir", str(cache), "--no-discovery"],
                        capture_output=True, text=True, timeout=10)
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertIn("colliding directory", json.loads(result.stdout)["error"])
                    self.assertFalse(cache.exists(), "invalid paths must fail before creating a cache")

    def test_shared_directory_spelling_remains_valid(self):
        manifest = self.manifest()
        manifest["files"] = [self.empty(path) for path in
                             ("Dir/a.txt", "Dir/nested/b.txt", "Dir/nested/c.txt", "cafe\u0301/a.txt", "cafe\u0301/b.txt")]
        self.assertEqual(validate_manifest(manifest), manifest)

    def test_reject_wrong_size_root_and_infohash(self):
        mutations = [("size", self.entry["size"] + 1), ("pieces_root", "0" * 64)]
        for field, value in mutations:
            manifest = self.manifest()
            manifest["files"][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_manifest(manifest)
        manifest = self.manifest()
        manifest["files"][0]["torrent"]["infohash_v2"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "infohash"):
            validate_manifest(manifest)

    def test_reject_invalid_piece_layer_outside_infohash(self):
        data = copy.deepcopy(self.torrent)
        key = next(iter(data[b"piece layers"]))
        layer = data[b"piece layers"][key]
        data[b"piece layers"][key] = bytes([layer[0] ^ 255]) + layer[1:]
        manifest = self.manifest()
        manifest["files"][0]["torrent"]["metadata"] = base64.b64encode(lt.bencode(data)).decode()
        with self.assertRaisesRegex(ValueError, "piece layer"):
            validate_manifest(manifest)

    def test_reject_embedded_sources_and_extra_files(self):
        for field, value in ((b"url-list", b"http://example.com/model"), (b"announce", b"http://tracker.test"), (b"nodes", [[b"example.com", 6881]])):
            data = copy.deepcopy(self.torrent)
            data[field] = value
            manifest = self.manifest()
            manifest["files"][0]["torrent"]["metadata"] = base64.b64encode(lt.bencode(data)).decode()
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_manifest(manifest)
        data = copy.deepcopy(self.torrent)
        data[b"info"][b"file tree"][b"hidden.py"] = {b"": {b"length": 1, b"pieces root": b"x" * 32}}
        manifest = self.manifest()
        manifest["files"][0]["torrent"]["metadata"] = base64.b64encode(lt.bencode(data)).decode()
        with self.assertRaisesRegex(ValueError, "file tree"):
            validate_manifest(manifest)

    def test_reject_missing_piece_layer_and_bad_base64(self):
        data = copy.deepcopy(self.torrent)
        data[b"piece layers"] = {}
        manifest = self.manifest()
        manifest["files"][0]["torrent"]["metadata"] = base64.b64encode(lt.bencode(data)).decode()
        with self.assertRaisesRegex(ValueError, "piece layer"):
            validate_manifest(manifest)
        manifest["files"][0]["torrent"]["metadata"] = "not base64!"
        with self.assertRaisesRegex(ValueError, "base64"):
            validate_manifest(manifest)

    def test_reject_unsupported_fields_types_and_urls(self):
        for mutation in (lambda m: m.update(schema="future"), lambda m: m.update(name="../outside"),
                         lambda m: m.update(version="../outside"), lambda m: m.update(extra=1),
                         lambda m: m["files"][0].update(size=True), lambda m: m["files"][0].update(size=1 << 41)):
            manifest = self.manifest()
            mutation(manifest)
            with self.assertRaises(ValueError):
                validate_manifest(manifest)
        for url in ("file:///tmp/model", "https://user:secret@host/file", "https://host/file#fragment", "https://host:99999/file", "http://host/\nfile"):
            manifest = self.manifest()
            manifest["files"][0]["sources"][0]["url"] = url
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_manifest(manifest)

    def test_reject_unsupported_payload_urls_before_alternate_sources(self):
        for url, error in (("https://mirror.example/weights.gguf?download=1", "query parameters"),
                           ("https://mirror.example/weights.gguf?", "query parameters"),
                           ("https://mirror.example/download", "model file name")):
            with self.subTest(url=url):
                manifest = self.manifest()
                manifest["files"][0]["sources"].insert(0, {"type": "http", "url": url})
                with self.assertRaisesRegex(ValueError, error):
                    validate_manifest(manifest)

    def test_encoded_payload_names_and_manifest_url_queries_remain_valid(self):
        manifest = self.manifest()
        manifest["files"][0]["sources"] = [{"type": "http", "url": "https://mirror.example/weights%2Egguf"}]
        self.assertEqual(validate_manifest(manifest), manifest)
        reference = "https://mirror.example/release.json?download=1"
        self.assertEqual(validate_source_url(reference), reference)

    def test_piece_aligned_torrent_allows_alternate_url_basename(self):
        source = self.root / "aligned.gguf"
        source.write_bytes(b"GGUF\x03\x00\x00\x00" + b"\x00" * (16 * 1024 - 8))
        manifest = self.manifest()
        manifest["files"] = [describe_file(source, source.name, "gguf",
                            [{"type": "http", "url": "https://mirror.example/alias.gguf"}],
                            piece_size=16 * 1024)]
        self.assertEqual(validate_manifest(manifest), manifest)

    def test_reject_duplicate_json_and_oversized_manifest(self):
        path = self.root / "bad.json"
        path.write_text('{"schema":"x","schema":"y"}')
        with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
            load_manifest(path)
        with path.open("wb") as stream:
            stream.seek(MAX_MANIFEST_BYTES)
            stream.write(b" ")
        with self.assertRaisesRegex(ValueError, "16 MiB"):
            load_manifest(path)


if __name__ == "__main__":
    unittest.main()
