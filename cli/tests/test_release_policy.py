"""Exercise signed-release network restrictions in libtorrent, without PKC nodes."""

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import libtorrent as lt

from modelswarm.cli import main
from modelswarm.engine import check_file, describe_file, download_file, peer_address
from modelswarm.manifest import SCHEMA, encode_manifest
from test_cli import gguf, http_source, peers


class ReleaseNetworkPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.source = self.root / "source"
        self.source.mkdir()
        self.model = self.source / "tiny.gguf"
        gguf(self.model, 96 * 1024 + 319)
        self.entry = describe_file(self.model, self.model.name, "gguf", [], piece_size=16 * 1024)

    def pull_signed(self, cache, peer, *options):
        manifest = {"schema": SCHEMA, "name": "owner/model", "version": "v0",
                    "license": "MIT", "files": [self.entry]}
        digest = hashlib.sha256(encode_manifest(manifest)).hexdigest()
        stdout, stderr = io.StringIO(), io.StringIO()
        with (patch("modelswarm.releases.resolve", return_value=(manifest, digest, {"signed": True})),
              redirect_stdout(stdout), redirect_stderr(stderr)):
            code = main(["pull", "pkc://publisher/owner/model@v0", "--cache-dir", str(cache),
                         "--no-discovery", "--peer", peer, *options])
        return code, json.loads(stdout.getvalue())

    def transfer(self, entry, name, *, allow_local_sources, peer_list=(), timeout=10):
        directory = self.root / name
        directory.mkdir()
        events = []
        emit = lambda event, **fields: events.append({"event": event, **fields})
        arguments = {
            "peers": peer_list, "discovery": False, "timeout": timeout, "rate": 0,
            "checkpoint_interval": 30, "cancel": threading.Event(), "emit": emit,
            "allow_local_sources": allow_local_sources,
        }
        return directory, events, lambda: download_file(entry, directory, **arguments)

    def assert_blocked(self, directory, events, run):
        with self.assertRaisesRegex(TimeoutError, "timeout downloading"):
            run()
        self.assertTrue(any(event["event"] == "file_ready" for event in events), events)
        self.assertFalse(any(event["event"] == "file_complete" for event in events), events)
        progress = [event for event in events if event["event"] == "progress"]
        self.assertTrue(progress, "transfer must run long enough to observe native byte counters")
        self.assertTrue(all(event["payload_bytes_since_resume"] == 0 for event in progress), progress)
        checkpoints = [event for event in events if event["event"] == "checkpoint_saved"]
        self.assertEqual(len(checkpoints), 1, events)
        self.assertEqual(checkpoints[0]["reason"], "timeout")
        self.assertEqual(checkpoints[0]["verified_pieces"], 0)
        resume = lt.read_resume_data((directory / "resume.data").read_bytes())
        self.assertFalse(any(resume.have_pieces))

    def test_restricted_webseed_blocks_loopback_ip_and_native_dns_resolution(self):
        # No manifest/DNS preflight runs here. These URLs reach the engine directly,
        # so zero HTTP requests establishes that libtorrent applies the IP filter.
        with http_source(self.source) as (base, requests):
            for index, origin in enumerate((base, base.replace("127.0.0.1", "localhost"))):
                with self.subTest(origin=origin):
                    entry = {**self.entry, "sources": [{"type": "http", "url": origin + self.model.name}]}
                    directory, events, run = self.transfer(
                        entry, f"http-blocked-{index}", allow_local_sources=False, timeout=2.1)
                    self.assert_blocked(directory, events, run)
                    self.assertEqual(requests, [])
        self.assertEqual(requests, [])

    def test_explicit_local_sources_allows_the_same_http_webseed(self):
        with http_source(self.source) as (base, requests):
            entry = {**self.entry, "sources": [{"type": "http", "url": base + self.model.name}]}
            _, events, run = self.transfer(entry, "http-allowed", allow_local_sources=True)
            path = run()
            check_file(entry, path)
            self.assertEqual(path.read_bytes(), self.model.read_bytes())
            complete = [event for event in events if event["event"] == "file_complete"]
            self.assertEqual(len(complete), 1, events)
            self.assertGreater(complete[0]["payload_bytes_since_resume"], 0)
        self.assertGreater(sum(request["sent"] for request in requests), 0)

    def test_restricted_peer_blocks_loopback_without_payload_upload(self):
        with peers({"files": [self.entry]}, self.source) as (peer, handles):
            directory, events, run = self.transfer(
                self.entry, "peer-blocked", allow_local_sources=False,
                peer_list=[peer_address(peer)], timeout=2.1)
            self.assert_blocked(directory, events, run)
            self.assertEqual(sum(handle.status().total_payload_upload for handle in handles), 0)
            self.assertEqual(sum(handle.status().total_upload for handle in handles), 0)

    def test_signed_pull_refuses_explicit_nonpublic_peers_before_transfer(self):
        with peers({"files": [self.entry]}, self.source) as (peer, handles):
            endpoints = (peer, peer.replace("127.0.0.1", "localhost"), "[::1]:6881",
                         "100.64.0.1:6881", "[fd7a:115c:a1e0::1]:6881", "[::ffff:8.8.8.8]:6881")
            for index, endpoint in enumerate(endpoints):
                with self.subTest(endpoint=endpoint):
                    cache = self.root / f"blocked-{index}"
                    code, result = self.pull_signed(cache, endpoint, "--timeout", "0.1")
                    self.assertEqual(code, 1, result)
                    self.assertIn(endpoint, result["error"])
                    self.assertIn("--allow-local-sources", result["error"])
                    self.assertFalse(cache.exists())
            self.assertEqual(sum(handle.status().total_payload_upload for handle in handles), 0)
            self.assertEqual(sum(handle.status().total_upload for handle in handles), 0)

    def test_signed_pull_with_local_sources_allows_the_same_loopback_peer(self):
        with peers({"files": [self.entry]}, self.source) as (peer, handles):
            code, result = self.pull_signed(self.root / "allowed", peer, "--allow-local-sources", "--timeout", "10")
            self.assertEqual(code, 0, result)
            self.assertTrue(result["signed"])
            path = Path(result["snapshot"]) / self.model.name
            self.assertEqual(path.read_bytes(), self.model.read_bytes())
            self.assertGreater(sum(handle.status().total_payload_upload for handle in handles), 0)


if __name__ == "__main__":
    unittest.main()
