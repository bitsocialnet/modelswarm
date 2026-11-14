"""Explicit but empty pins must never become unpinned discovery."""

from contextlib import redirect_stdout
import io
import json
import unittest
from unittest.mock import patch

from modelswarm.cli import main
from modelswarm.releases import parse_uri, resolve


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


if __name__ == "__main__":
    unittest.main()
