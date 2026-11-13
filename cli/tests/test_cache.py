import hashlib
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from modelswarm.cache import cache_root, cached_files, ensure_directory, materialize, snapshot_revision


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        # macOS exposes the system temp directory through /var -> /private/var.
        self.root = Path(self.temporary.name).resolve()
        self.cache = self.root / "cache"
        self.inputs = self.root / "inputs"
        self.inputs.mkdir()
        self.digest = "a" * 64

    def tearDown(self):
        self.temporary.cleanup()

    def fixture(self, content):
        entries, verified = [], {}
        for index, (relative, data) in enumerate(content.items()):
            source = self.inputs / f"input-{index}"
            source.write_bytes(data)
            entry = {"path": relative, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            entries.append(entry)
            verified[relative] = source
        return {"name": "owner/model", "files": entries}, verified

    def test_nested_snapshot_and_repeat_preserve_blobs(self):
        manifest, verified = self.fixture({"config.json": b"{}", "nested/weights.gguf": b"GGUF-test"})
        snapshot = materialize(self.cache, manifest, self.digest, verified)
        self.assertEqual(snapshot, self.cache / "models--owner--model" / "snapshots" / ("a" * 40))
        self.assertEqual((snapshot / "nested/weights.gguf").read_bytes(), b"GGUF-test")
        self.assertTrue((snapshot / "config.json").is_symlink())
        blob = self.cache / "models--owner--model" / "blobs" / manifest["files"][0]["sha256"]
        inode = blob.stat().st_ino
        self.assertEqual(materialize(self.cache, manifest, self.digest, verified), snapshot)
        self.assertEqual(blob.stat().st_ino, inode)
        self.assertFalse((snapshot.parent.parent / "refs").exists())

    def test_safe_subset_then_full_selection(self):
        manifest, verified = self.fixture({"config.json": b"{}", "model.py": b"print('never executed')"})
        snapshot = materialize(self.cache, manifest, self.digest, {"config.json": verified["config.json"]})
        self.assertFalse((snapshot / "model.py").exists())
        materialize(self.cache, manifest, self.digest, verified)
        self.assertEqual((snapshot / "model.py").read_bytes(), b"print('never executed')")

    def test_all_inputs_verify_before_snapshot_extension(self):
        manifest, verified = self.fixture({"old.txt": b"old", "new.txt": b"new", "bad.txt": b"expected"})
        snapshot = materialize(self.cache, manifest, self.digest, {"old.txt": verified["old.txt"]})
        verified["bad.txt"].write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "does not match"):
            materialize(self.cache, manifest, self.digest, verified)
        self.assertFalse((snapshot / "new.txt").exists())
        self.assertEqual((snapshot / "old.txt").read_bytes(), b"old")

    def test_cache_ancestor_symlink_is_rejected(self):
        manifest, verified = self.fixture({"file.txt": b"value"})
        outside = self.root / "outside"
        outside.mkdir()
        self.cache.symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "real directory"):
            materialize(self.cache, manifest, self.digest, verified)
        self.assertEqual(list(outside.iterdir()), [])

    def test_blob_symlink_and_hardlink_do_not_modify_outside_file(self):
        manifest, verified = self.fixture({"file.txt": b"value"})
        blobs = ensure_directory(self.cache / "models--owner--model" / "blobs")
        blob = blobs / manifest["files"][0]["sha256"]
        outside = self.root / "outside.txt"
        outside.write_bytes(b"value")
        blob.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "regular private"):
            materialize(self.cache, manifest, self.digest, verified)
        blob.unlink()
        os.link(outside, blob)
        # Existing content is only read. Never overwrite/repair a hardlinked blob.
        materialize(self.cache, manifest, self.digest, verified)
        self.assertEqual(outside.read_bytes(), b"value")
        outside.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "does not match"):
            materialize(self.cache, manifest, self.digest, verified)
        self.assertEqual(outside.read_bytes(), b"changed")

    def test_corrupted_blob_is_rejected_without_replacement(self):
        manifest, verified = self.fixture({"file.txt": b"value"})
        snapshot = materialize(self.cache, manifest, self.digest, verified)
        blob = (snapshot / "file.txt").resolve()
        blob.write_bytes(b"wrong")
        with self.assertRaisesRegex(ValueError, "does not match"):
            materialize(self.cache, manifest, self.digest, verified)
        self.assertEqual(blob.read_bytes(), b"wrong")

    def test_snapshot_directory_symlink_is_rejected(self):
        manifest, verified = self.fixture({"nested/file.txt": b"value"})
        snapshot = materialize(self.cache, manifest, self.digest, verified)
        (snapshot / "nested/file.txt").unlink()
        (snapshot / "nested").rmdir()
        outside = self.root / "outside"
        outside.mkdir()
        (snapshot / "nested").symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "unexpected snapshot directory"):
            materialize(self.cache, manifest, self.digest, verified)
        self.assertEqual(list(outside.iterdir()), [])

    def test_foreign_snapshot_entries_are_preserved_and_rejected(self):
        manifest, verified = self.fixture({"file.txt": b"value"})
        snapshot = materialize(self.cache, manifest, self.digest, verified)
        (snapshot / "foreign.txt").write_bytes(b"keep")
        with self.assertRaisesRegex(ValueError, "unexpected snapshot file"):
            materialize(self.cache, manifest, self.digest, verified)
        self.assertEqual((snapshot / "foreign.txt").read_bytes(), b"keep")

    def test_staged_symlink_is_rejected(self):
        manifest, verified = self.fixture({"file.txt": b"value"})
        target = self.inputs / "link"
        target.symlink_to(verified["file.txt"])
        with self.assertRaisesRegex(ValueError, "regular private"):
            materialize(self.cache, manifest, self.digest, {"file.txt": target})
        self.assertFalse(self.cache.exists())

    def test_revision_prefix_collision_is_rejected(self):
        manifest, verified = self.fixture({"file.txt": b"value"})
        materialize(self.cache, manifest, self.digest, verified)
        with self.assertRaisesRegex(ValueError, "another manifest"):
            materialize(self.cache, manifest, "a" * 40 + "b" * 24, verified)

    def test_cache_lookup_is_read_only_and_returns_regular_blob_sources(self):
        manifest, verified = self.fixture({"file.txt": b"value"})
        self.assertEqual(cached_files(self.cache, manifest, self.digest), {})
        self.assertFalse(self.cache.exists())
        snapshot = materialize(self.cache, manifest, self.digest, verified)
        found = cached_files(self.cache, manifest, self.digest)
        self.assertEqual(found["file.txt"], (snapshot / "file.txt").resolve())
        self.assertFalse(found["file.txt"].is_symlink())
        self.assertEqual(materialize(self.cache, manifest, self.digest, found), snapshot)

    def test_cache_lookup_rejects_tampered_snapshot(self):
        manifest, verified = self.fixture({"file.txt": b"value"})
        snapshot = materialize(self.cache, manifest, self.digest, verified)
        path = snapshot / "file.txt"
        path.unlink()
        path.symlink_to(self.inputs / "input-0")
        with self.assertRaisesRegex(ValueError, "expected blob link"):
            cached_files(self.cache, manifest, self.digest)

    def test_cache_lookup_can_reuse_blob_without_snapshot(self):
        manifest, verified = self.fixture({"file.txt": b"value"})
        blob = ensure_directory(self.cache / "models--owner--model" / "blobs") / manifest["files"][0]["sha256"]
        blob.write_bytes(b"value")
        self.assertEqual(cached_files(self.cache, manifest, self.digest), {"file.txt": blob})

    def test_path_escape_is_rejected(self):
        for relative in ("../outside", "nested/../../outside", "/absolute", "a\\b", "C:/outside", "a//b"):
            with self.subTest(relative=relative):
                manifest, verified = self.fixture({relative: b"value"})
                with self.assertRaisesRegex(ValueError, "unsafe"):
                    materialize(self.cache, manifest, self.digest, verified)

    def test_default_environment_and_revision_validation(self):
        with patch.dict(os.environ, {"MODELSWARM_CACHE": str(self.cache)}):
            self.assertEqual(cache_root(), self.cache)
            self.assertEqual(cache_root(self.root / "override"), self.root / "override")
        with self.assertRaises(ValueError):
            snapshot_revision("../bad")

    def test_parallel_manifests_can_reuse_blob_during_publication(self):
        manifest, verified = self.fixture({"file.txt": b"value"})
        published, release = threading.Event(), threading.Event()
        real_link = os.link

        def pause_after_blob_link(source, destination, **kwargs):
            real_link(source, destination, **kwargs)
            if Path(destination).parent.name == "blobs":
                published.set()
                if not release.wait(5):
                    raise TimeoutError("parallel publication test timed out")

        with patch("modelswarm.cache.os.link", side_effect=pause_after_blob_link):
            with ThreadPoolExecutor(max_workers=1) as executor:
                first = executor.submit(materialize, self.cache, manifest, self.digest, verified)
                try:
                    self.assertTrue(published.wait(5))
                    second = materialize(self.cache, manifest, "b" * 64, verified)
                    self.assertEqual((second / "file.txt").read_bytes(), b"value")
                finally:
                    release.set()
                self.assertEqual((first.result(timeout=5) / "file.txt").read_bytes(), b"value")


if __name__ == "__main__":
    unittest.main()
