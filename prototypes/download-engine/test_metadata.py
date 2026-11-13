"""Small adversarial metadata checks, independent of the network experiments."""

import hashlib
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
import subprocess
import sys

import libtorrent as lt

from engine import MIB, configure_params, make_torrent, verified_bytes, web_seed_url


class MetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.root = Path(cls.directory.name)
        cls.source = cls.root / "weights.bin"
        cls.source.write_bytes(hashlib.shake_256(b"metadata-fixture").digest(4 * MIB))
        cls.path = cls.root / "weights.torrent"
        cls.manifest = make_torrent(cls.source, cls.path)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def test_explicit_v2_and_expected_file_root(self):
        info = lt.torrent_info(self.path.read_bytes())
        self.assertTrue(info.info_hashes().has_v2())
        self.assertFalse(info.info_hashes().has_v1())
        self.assertEqual(str(info.files().root(0)), self.manifest["pieces_root"])

    def test_reject_piece_layer_outside_infohash(self):
        data = lt.bdecode(self.path.read_bytes())
        infohash = hashlib.sha256(lt.bencode(data[b"info"])).hexdigest()
        root = next(iter(data[b"piece layers"]))
        layer = data[b"piece layers"][root]
        data[b"piece layers"][root] = bytes([layer[0] ^ 255]) + layer[1:]
        self.assertEqual(hashlib.sha256(lt.bencode(data[b"info"])).hexdigest(), infohash)
        with self.assertRaisesRegex(RuntimeError, "piece layer is invalid"):
            lt.torrent_info(lt.bencode(data))

    def test_reject_resume_from_different_torrent(self):
        info = lt.torrent_info(self.path.read_bytes())
        other = self.root / "other.bin"
        other.write_bytes(b"different contents")
        other_torrent = self.root / "other.torrent"
        make_torrent(other, other_torrent)
        params = lt.add_torrent_params()
        params.ti = lt.torrent_info(other_torrent.read_bytes())
        params.info_hashes = params.ti.info_hashes()
        resume = self.root / "other.resume"
        resume.write_bytes(bytes(lt.write_resume_data_buf(params)))
        with self.assertRaisesRegex(ValueError, "different torrent"):
            configure_params(info, self.root, resume)

    def test_tail_padding_is_not_model_data(self):
        source = self.root / "unaligned.bin"
        source.write_bytes(b"x" * (MIB + 123))
        torrent = self.root / "unaligned.torrent"
        make_torrent(source, torrent)
        info = lt.torrent_info(torrent.read_bytes())
        self.assertGreater(info.num_files(), 1)
        status = SimpleNamespace(pieces=[True] * info.num_pieces())
        self.assertEqual(verified_bytes(info, status), source.stat().st_size)
        self.assertEqual(web_seed_url(info, "https://example.org/revision/unaligned.bin"),
                         "https://example.org/revision/")

    def test_partial_blocks_do_not_count_as_verified(self):
        info = lt.torrent_info(self.path.read_bytes())
        status = SimpleNamespace(pieces=[False] * info.num_pieces(), total_done=2 * MIB)
        self.assertEqual(verified_bytes(info, status), 0)

    def test_cli_rejects_untrusted_torrent_before_creating_destination(self):
        destination = self.root / "must-not-be-created"
        result = subprocess.run([sys.executable, str(Path(__file__).with_name("engine.py")),
                                 "download", str(self.path), str(destination),
                                 "--torrent-sha256", "0" * 64], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 1)
        self.assertIn("metadata does not match", result.stdout)
        self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
