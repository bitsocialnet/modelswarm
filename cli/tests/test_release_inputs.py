"""Publisher CLI input validation and key output handling."""

from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from modelswarm.cli import main
from modelswarm.releases import parse_uri, read_key, resolve


class ReleaseInputTests(unittest.TestCase):
    uri = "pkc://12D3KooW" + "a" * 44 + "/fixture/model@v1"

    def test_empty_cid_is_rejected_before_rpc(self):
        self.assertIsNone(parse_uri(self.uri)["cid"])
        with patch("modelswarm.releases.bridge") as bridge:
            with self.assertRaisesRegex(ValueError, "release URI"):
                resolve(self.uri + "#")
            bridge.assert_not_called()

    def test_invalid_digest_is_rejected_before_signed_resolution(self):
        for digest in ("", "not-a-digest", "A" * 64):
            with self.subTest(digest=digest), patch("modelswarm.releases.resolve") as resolver:
                output = io.StringIO()
                with redirect_stdout(output):
                    code = main(["pull", self.uri, "--manifest-sha256", digest])
                self.assertEqual(code, 1)
                self.assertIn("expected manifest SHA-256", json.loads(output.getvalue())["error"])
                resolver.assert_not_called()


class KeyOutputTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        self.parent = self.root / "keys"
        self.parent.mkdir()
        self.alias = self.root / "alias"
        self.alias.symlink_to(self.parent, target_is_directory=True)

    def keygen(self, name):
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(["keygen", "--output", str(self.alias / name)])
        return code, json.loads(output.getvalue())

    def test_allocates_private_key_through_immediate_parent_alias(self):
        private_key = "A" * 43
        with patch("modelswarm.releases.bridge", return_value={"privateKey": private_key, "publisher": "fixture"}):
            code, result = self.keygen("owner.json")
        self.assertEqual(code, 0, result)
        key = self.parent / "owner.json"
        self.assertEqual(Path(result["key_file"]), key)
        self.assertEqual(read_key(key), private_key)
        if os.name == "posix":
            self.assertEqual(stat.S_IMODE(key.stat().st_mode), 0o600)

    def test_existing_file_and_key_symlinks_are_preserved(self):
        existing = self.parent / "existing.json"
        existing.write_bytes(b"keep existing key")
        link, dangling = (self.parent / name for name in ("link.json", "dangling.json"))
        link.symlink_to(existing.name)
        dangling.symlink_to("missing.json")
        with patch("modelswarm.releases.bridge") as bridge:
            for key in (existing, link, dangling):
                with self.subTest(name=key.name):
                    code, result = self.keygen(key.name)
                    self.assertEqual(code, 1, result)
                    self.assertIn("refusing to replace", result["error"])
            bridge.assert_not_called()
        self.assertEqual(existing.read_bytes(), b"keep existing key")
        self.assertEqual(link.readlink(), Path(existing.name))
        self.assertEqual(dangling.readlink(), Path("missing.json"))
        self.assertFalse(dangling.exists())


if __name__ == "__main__":
    unittest.main()
