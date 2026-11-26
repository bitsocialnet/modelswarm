"""Sync a community and reply using a separate node in a private Kubo swarm."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import libtorrent as lt

from catalogue import community as exporter
from modelswarm.manifest import torrent_bytes
from pkc_fixture import FixtureNode
from test_persistence import PersistentNode


ROOT = Path(__file__).resolve().parents[2]


class CommunityExportTests(unittest.TestCase):
    def test_default_torrent_directory_is_relative_to_public(self):
        self.assertEqual(exporter.torrent_url_prefix(Path("public/community-torrents")), "./community-torrents")
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "inside the site's public directory"):
                exporter.torrent_url_prefix(Path(directory))

    def test_incomplete_scan_preserves_existing_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "community-index.json"
            old = b'{"version":1,"entries":[{"name":"existing/model"}]}\n'
            output.write_bytes(old)
            args = SimpleNamespace(community="hub", rpc_timeout=30, output=output, torrent_dir=Path("public/hub-torrents"))
            with patch.object(exporter, "bridge", return_value={"truncated": True, "entries": []}):
                with self.assertRaisesRegex(ValueError, "scan is incomplete"):
                    exporter.sync(args, "ws://127.0.0.1")
            self.assertEqual(output.read_bytes(), old)


class CommunityCatalogueTests(PersistentNode, unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.dict(os.environ, {"MODELSWARM_TEST_PUBSUB": "1"}))
        super().setUp()

    def run_community(self, node, *args, cwd=ROOT):
        command = [sys.executable, str(ROOT / "catalogue/community.py"), *map(str, args),
                   "--rpc", node["rpc_url"], "--rpc-timeout", "30"]
        env = {**self.environment, "PYTHONPATH": str(ROOT / "cli/src")}
        result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, timeout=50)
        self.assert_no_secrets(result.stdout + result.stderr)
        self.assertNotIn(node["rpc_url"], result.stdout + result.stderr)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def snapshot_when(self, node, community, directory, predicate):
        directory.mkdir(exist_ok=True)
        output = directory / "community-index.json"
        for _ in range(10):
            self.run_community(node, "sync", community, "--output", output,
                               "--torrent-dir", "public/hub-torrents", cwd=directory)
            snapshot = json.loads(output.read_text())
            self.assertEqual(snapshot["community"], community)
            if predicate(snapshot["entries"]):
                return snapshot["entries"]
            time.sleep(1)
        self.fail(f"Community snapshot did not receive expected updates: {snapshot}")

    def test_new_release_and_reader_reply_cross_the_private_swarm(self):
        community = self.run_community(self.fixture, "init", "--key", self.key)["community"]
        node = FixtureNode(self.root / "reader", self.root / "reader.log", kubo_bin=self.node.kubo_bin,
                           node_bin=self.node.node_bin, swarm_key=self.node.data / "kubo" / "swarm.key",
                           peers=self.fixture["swarm"])
        self.addCleanup(node.kill)
        reader = node.start()
        self.assertNotEqual(reader["rpc_url"], self.fixture["rpc_url"])
        reader_dir = self.root / "reader-site"
        self.snapshot_when(reader, community, reader_dir, lambda entries: entries == [])

        manifest = self.root / "peer-release.json"
        self.command("make", self.source, "-o", manifest, "--name", "fixture/model", "--version", "community-v1",
                     "--license", "apache-2.0")
        published = self.publish(manifest=manifest, manifest_url=self.ipfs_add(manifest), allow_local=False)
        share = self.run_community(self.fixture, "share", community, published["release_uri"], "--key", self.key)
        [entry] = self.snapshot_when(reader, community, reader_dir, bool)
        self.assertEqual(entry["name"], "fixture/model")
        self.assertEqual(entry["publisher"], self.publisher)
        self.assertEqual(entry["releaseCid"], published["release_cid"])
        self.assertEqual(entry["postCid"], share["postCid"])
        self.assertNotEqual(share["postCid"], share["releaseCid"])

        expected = next(file for file in json.loads(manifest.read_text())["files"] if file["path"] == "weights.gguf")
        script = next(file for file in entry["files"] if file["path"] == "custom.py")
        self.assertTrue(script["flagged"])
        self.assertIsNone(script["torrent"])
        self.assertIsNone(script["https"])
        weights = next(file for file in entry["files"] if file["path"] == "weights.gguf")
        self.assertEqual(weights["sha256"], expected["sha256"])
        self.assertEqual(weights["torrent"], f"./hub-torrents/{expected['torrent']['infohash_v2']}.torrent")
        metainfo = reader_dir / "public" / weights["torrent"].removeprefix("./")
        self.assertEqual(metainfo.read_bytes(), torrent_bytes(expected))
        self.assertEqual(str(lt.torrent_info(str(metainfo)).info_hashes().v2), expected["torrent"]["infohash_v2"])

        reply_key = self.root / "reader-user.key.json"
        author = self.command("keygen", "-o", reply_key)["publisher"]
        reply = self.run_community(reader, "reply", community, share["postCid"], "--key", reply_key,
                                   "--text", "I found the release from my own reader.")
        for rpc, directory in ((self.fixture, self.root / "host-site"), (reader, reader_dir)):
            [with_reply] = self.snapshot_when(rpc, community, directory, lambda entries: entries and entries[0]["replies"])
            self.assertEqual(with_reply["replies"], [reply])
            self.assertEqual(reply["author"], author)
        self.assertEqual(self.requests, [], "neither instance should consult an HTTP model source")
        node.stop()
        self.node.stop()
