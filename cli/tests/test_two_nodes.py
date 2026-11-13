"""A reader's own PKC node resolving a publisher hosted on a different node.

Both nodes run on this machine in one private swarm. Unlike every other release
test, the reader never talks to the publisher's RPC: the delegation, profile
record, pages and release records all cross the Kubo swarm connection.
"""

from contextlib import contextmanager
import json
import unittest

from pkc_fixture import FixtureNode
from test_cli import peers
from test_persistence import PersistentNode


class TwoNodeTests(PersistentNode, unittest.TestCase):
    def setUp(self):
        super().setUp()
        directory = self.node.data.parent
        self.reader_node = FixtureNode(directory / "reader", directory / "reader.log", kubo_bin=self.node.kubo_bin,
                                       node_bin=self.node.node_bin, swarm_key=self.node.data / "kubo" / "swarm.key",
                                       peers=self.fixture["swarm"])
        self.addCleanup(self.reader_node.kill)
        self.reader = self.reader_node.start()
        self.assertNotEqual(self.reader["kubo_pid"], self.fixture["kubo_pid"])

    @contextmanager
    def through_reader(self):
        publisher_node, self.fixture = self.fixture, self.reader
        try:
            yield
        finally:
            self.fixture = publisher_node

    def read(self, uri, *, cache, file=None):
        with self.through_reader():
            return self.pull_when_discoverable(uri, cache=cache, file=file or "config.json")

    def test_reader_node_resolves_and_verifies_releases_it_does_not_host(self):
        published = self.publish()
        by_version = self.read(published["release_uri"].split("#")[0], cache="reader-version")
        self.assert_snapshot(by_version, ["config.json"])
        self.assertEqual(by_version["release_cid"], published["release_cid"])
        with self.through_reader():
            by_cid = self.pull(published["release_uri"], cache="reader-cid")
            self.assert_snapshot(by_cid, ["config.json", "weights.gguf", "nested/readme.txt", "empty.txt"])
            # A reader's node holds neither the minter nor any authority over the profile.
            for refused in (self.command("profile-start", self.publisher, *self.rpc_options(), ok=False),
                            self.command("profile-renew", "--key", self.key, "--minter", self.minter,
                                         *self.rpc_options(), ok=False)):
                self.assertIn("does not host", refused["error"])
            second = self.root / "release-2.json"
            self.make(second, version="release-2")
            refused = self.publish(manifest=second, ok=False)
            self.assertIn("delegated profile on this RPC node", refused["error"])
            other = self.command("keygen", "-o", self.root / "other.key.json")
            self.secrets.append(json.loads((self.root / "other.key.json").read_text())["privateKey"])
            refused = self.pull(published["release_uri"].replace(self.publisher, other["publisher"], 1), ok=False)
            self.assertIn("signature verification failed", refused["error"])

    def test_reader_needs_no_http_with_ipfs_manifest_and_peer_only_weights(self):
        # The shape a reader on another machine needs: nothing below depends on
        # an HTTP server it could only reach on the publisher's loopback.
        manifest = self.root / "peer-only.json"
        self.command("make", self.source, "-o", manifest, "--name", "fixture/model", "--version", "peer-only",
                     "--license", "apache-2.0")
        published = self.publish(manifest=manifest, manifest_url=self.ipfs_add(manifest))
        self.assertEqual(self.requests, [])
        with peers(json.loads(manifest.read_text()), self.source) as (peer, handles), self.through_reader():
            pulled = self.command("pull", published["release_uri"], *self.rpc_options(), "--allow-local-sources",
                                  "--no-discovery", "--peer", peer, "--cache-dir", self.root / "peer-only-cache",
                                  "--timeout", "30", "--file", "weights.gguf", "--file", "nested/readme.txt")
            self.assertGreater(sum(handle.status().total_payload_upload for handle in handles), 0)
        self.assert_snapshot(pulled, ["weights.gguf", "nested/readme.txt"])
        self.assertEqual(pulled["release_cid"], published["release_cid"])
        self.assertEqual(self.requests, [], "nothing may be fetched over HTTP")

    def test_reader_follows_publisher_restart_renewal_and_new_release(self):
        first = self.publish()
        version_uri = first["release_uri"].split("#")[0]
        self.assertEqual(self.read(version_uri, cache="before")["release_cid"], first["release_cid"])

        self.restart(abrupt=False)
        self.assertEqual(self.command("profile-renew", "--key", self.key, "--minter", self.minter,
                                      *self.rpc_options())["sequence"], "5")
        second_manifest = self.root / "release-2.json"
        self.make(second_manifest, version="release-2")
        second = self.publish(manifest=second_manifest)
        # Published after the restart and renewal, so only the restarted
        # publisher node can have told the reader's node about it.
        discovered = self.read(second["release_uri"].split("#")[0], cache="after-restart")
        self.assert_snapshot(discovered, ["config.json"])
        self.assertEqual(discovered["release_cid"], second["release_cid"])
        self.assertEqual(self.read(version_uri, cache="after-restart-first")["release_cid"], first["release_cid"])

        self.reader_node.stop()
        self.reader = self.reader_node.start(resume=True)
        # A release the restarted reader node has never seen: it must reconnect to learn of it.
        third_manifest = self.root / "release-3.json"
        self.make(third_manifest, version="release-3")
        third = self.publish(manifest=third_manifest)
        self.assertEqual(self.read(third["release_uri"].split("#")[0], cache="reader-restarted")["release_cid"],
                         third["release_cid"])


if __name__ == "__main__":
    unittest.main()
