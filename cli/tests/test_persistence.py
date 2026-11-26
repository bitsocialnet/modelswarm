"""A publisher node stopped or killed and restarted over the same data directory."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

from modelswarm.releases import BRIDGE
from pkc_fixture import FixtureNode
from test_releases import ReleaseCommands, required_kubo


PROFILE_STATE = """
import PKC from '@pkcprotocol/pkc-js';
let input=''; for await(const chunk of process.stdin)input+=chunk;
const request=JSON.parse(input);
const pkc=await PKC({noData:true,pkcRpcClientsOptions:[request.rpc],kuboRpcClientsOptions:[],
  pubsubKuboRpcClientsOptions:[],httpRoutersOptions:[],ipfsGatewayUrls:[],resolveAuthorNames:false});
pkc.on('error',()=>{});
try {
  const profile=await pkc.createCommunity({publicKey:request.publisher});
  console.log(JSON.stringify({minter:profile.signer?.address,anchor:profile.anchor?.publicKey,
    sequence:profile.anchorRecordSequence,started:profile.started===true}));
} finally { await pkc.destroy(); }
"""


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


class PersistentNode(ReleaseCommands):
    """Owns one restartable fixture node and one publisher profile per test."""

    swarm_listen = None  # loopback unless a subclass must be reachable from another machine

    def setUp(self):
        artifacts = Path(__file__).resolve().parents[2] / ".tmp"
        artifacts.mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix="pkc-persist-", dir=artifacts)
        self.addCleanup(temporary.cleanup)
        directory = Path(temporary.name)
        self.node = FixtureNode(directory / "data", directory / "fixture.log", kubo_bin=required_kubo(),
                                node_bin=os.environ.get("MODELSWARM_NODE"), swarm_listen=self.swarm_listen)
        # Registered after the directory cleanup so it runs first, even when a
        # test fails between a kill and the following restart.
        self.addCleanup(self.node.kill)
        self.fixture = self.node.start()
        self.prepare_workspace(directory)
        self.create_profile()

    def profile_state(self):
        result = subprocess.run([os.environ.get("MODELSWARM_NODE", "node"), "--input-type=module", "-e", PROFILE_STATE],
                                cwd=BRIDGE.parent, input=json.dumps({"rpc": self.fixture["rpc_url"],
                                                                   "publisher": self.publisher}),
                                capture_output=True, text=True, env=self.environment, timeout=30)
        self.assert_no_secrets(result.stdout + result.stderr)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def restart(self, *, abrupt):
        """Stop or SIGKILL the node and resume it at once on the same data.

        Since pkc-js 0.0.154 the kernel holds the profile's start lock, so a
        killed process frees it as it dies and the restarted node hosts the
        profile again by itself. A lock that outlives its process fails here.
        """
        previous = self.fixture
        if abrupt:
            self.node.kill()
        else:
            self.node.stop()
        deadline = time.monotonic() + 10
        while alive(previous["pid"]) or alive(previous["kubo_pid"]):
            self.assertLess(time.monotonic(), deadline, "fixture processes survived shutdown")
            time.sleep(0.05)
        self.fixture = self.node.start(resume=True)
        self.assertTrue(self.fixture["resumed"])
        self.assertEqual(self.fixture["data_dir"], previous["data_dir"])
        deadline = time.monotonic() + 60
        while not (state := self.profile_state())["started"]:
            self.assertLess(time.monotonic(), deadline, "restarted node did not resume hosting the profile")
            time.sleep(0.25)
        # `started` would also read true under a start lock the stopped process
        # still held. profile-start succeeds only by attaching to a profile this
        # node runs; under another holder's lock it fails with ALREADY_STARTED.
        started = self.command("profile-start", self.publisher, *self.rpc_options())
        self.assertEqual(started["minter"], self.minter)
        return state

    def pull_when_discoverable(self, uri, **options):
        """Version discovery of a release announced right after a restart.

        Since pkc-js 0.0.149 a restarted minter publishes its next record
        without first resolving its own IPNS name, which the isolated Kubo held
        for 60 seconds. The release joins the profile feed within seconds; the
        deadline fails a return of that delay.
        """
        deadline = time.monotonic() + 30
        while True:
            result = self.command("pull", uri, *self.rpc_options(), "--allow-local-sources", "--no-discovery",
                                  "--cache-dir", self.root / options["cache"], "--timeout", "15",
                                  "--file", options["file"], ok=None)
            if result.get("ok"):
                return result
            self.assertIn("No verified publisher release", result["error"])
            self.assertLess(time.monotonic(), deadline, "release never became discoverable by version")
            time.sleep(2)


class RestartTests(PersistentNode, unittest.TestCase):
    def check_restart(self, *, abrupt):
        first = self.publish()
        by_version = self.pull(first["release_uri"].split("#")[0], cache="before", file="config.json")
        self.assertEqual(by_version["release_cid"], first["release_cid"])
        before = self.profile_state()
        self.assertEqual(before, {"minter": self.minter, "anchor": self.publisher, "sequence": "0", "started": True})

        after = self.restart(abrupt=abrupt)
        self.assertEqual(after, before)

        # Fresh caches: nothing below can be satisfied by pre-restart state.
        by_version = self.pull(first["release_uri"].split("#")[0], cache="after-version", file="nested/readme.txt")
        self.assert_snapshot(by_version, ["nested/readme.txt"])
        self.assertEqual(by_version["release_cid"], first["release_cid"])
        by_cid = self.pull(first["release_uri"], cache="after-cid")
        self.assert_snapshot(by_cid, ["config.json", "weights.gguf", "nested/readme.txt", "empty.txt"])
        self.assertEqual(by_cid["release_cid"], first["release_cid"])

        retried = self.publish()
        self.assertTrue(retried["reused"])
        self.assertEqual(retried["release_cid"], first["release_cid"])
        refused = self.command("profile-init", "--key", self.key, *self.rpc_options(), ok=False)
        self.assertIn("anchor record", refused["error"].lower())

        second_manifest = self.root / "release-2.json"
        self.make(second_manifest, version="release-2")
        second = self.publish(manifest=second_manifest)
        self.assertFalse(second["reused"])
        self.assertNotEqual(second["release_cid"], first["release_cid"])
        pinned = self.pull(second["release_uri"], cache="after-fresh-cid", file="config.json")
        self.assert_snapshot(pinned, ["config.json"])
        fresh = self.pull_when_discoverable(second["release_uri"].split("#")[0], cache="after-fresh", file="config.json")
        self.assert_snapshot(fresh, ["config.json"])
        self.assertEqual(fresh["release_cid"], second["release_cid"])
        self.assertEqual(self.profile_state(), before)
        return first, second

    def test_graceful_restart_keeps_profile_releases_and_accepts_new_ones(self):
        self.check_restart(abrupt=False)

    def test_immediate_restarts_keep_both_releases(self):
        first, second = self.check_restart(abrupt=True)
        # A second crash, immediately after the post-restart publication.
        before = self.profile_state()
        self.assertEqual(self.restart(abrupt=True), before)
        for published in (first, second):
            pulled = self.pull(published["release_uri"].split("#")[0],
                               cache="twice-" + published["release_cid"][-8:], file="config.json")
            self.assert_snapshot(pulled, ["config.json"])
            self.assertEqual(pulled["release_cid"], published["release_cid"])

    def test_profile_start_is_idempotent_and_refuses_profiles_the_node_does_not_host(self):
        started = self.command("profile-start", self.publisher, *self.rpc_options())
        self.assertEqual(started, {"command": "profile-start", "publisher": self.publisher, "minter": self.minter,
                                   "started": True, "ok": True})
        other = self.command("keygen", "-o", self.root / "other.key.json")
        self.secrets.append(json.loads((self.root / "other.key.json").read_text())["privateKey"])
        refused = self.command("profile-start", other["publisher"], *self.rpc_options(), ok=False)
        self.assertIn("does not host", refused["error"])
        published = self.publish()
        self.assert_snapshot(self.pull(published["release_uri"], file="config.json"), ["config.json"])


ANCHOR_ATTEMPTS = """
import PKC, { createAnchorIpnsRecord } from '@pkcprotocol/pkc-js';
let input=''; for await(const chunk of process.stdin)input+=chunk;
const request=JSON.parse(input);
const pkc=await PKC({noData:true,pkcRpcClientsOptions:[request.rpc],kuboRpcClientsOptions:[],
  pubsubKuboRpcClientsOptions:[],httpRoutersOptions:[],ipfsGatewayUrls:[],resolveAuthorNames:false});
pkc.on('error',()=>{});
try {
  const owner=await pkc.createSigner({type:'ed25519',privateKey:request.privateKey});
  const stranger=await pkc.createSigner();
  const profile=await pkc.createCommunity({publicKey:owner.address});
  profile.on('error',()=>{});
  const minter=profile.signer.address;
  const attempts={
    replayed:{anchorSigner:owner,minterIpnsName:minter,sequence:request.replay},
    equal:{anchorSigner:owner,minterIpnsName:minter,sequence:profile.anchorRecordSequence},
    foreignMinter:{anchorSigner:owner,minterIpnsName:stranger.address,sequence:'1000'},
    foreignSigner:{anchorSigner:stranger,minterIpnsName:minter,sequence:'1000'},
  };
  const outcome={};
  for(const [name,options] of Object.entries(attempts)) {
    try { await profile.publishAnchorRecord(await createAnchorIpnsRecord(options)); outcome[name]='accepted'; }
    catch(error) { outcome[name]=String(error.code); }
  }
  console.log(JSON.stringify({outcome,sequence:profile.anchorRecordSequence}));
} finally { await pkc.destroy(); }
"""


class RenewalTests(PersistentNode, unittest.TestCase):
    def renew(self, ok=True, key=None, minter=None):
        return self.command("profile-renew", "--key", key or self.key, "--minter", minter or self.minter,
                            *self.rpc_options(), ok=ok)

    def state(self, sequence):
        return {"minter": self.minter, "anchor": self.publisher, "sequence": sequence, "started": True}

    def test_renewal_advances_the_delegation_without_disturbing_releases(self):
        first = self.publish()
        renewed = self.renew()
        self.assertEqual(renewed, {"command": "profile-renew", "publisher": self.publisher, "minter": self.minter,
                                   "sequence": "5", "previous_sequence": "0", "ok": True})
        self.assertEqual(self.profile_state(), self.state("5"))
        by_version = self.pull(first["release_uri"].split("#")[0], cache="renewed-version", file="config.json")
        self.assertEqual(by_version["release_cid"], first["release_cid"])
        self.assert_snapshot(self.pull(first["release_uri"], cache="renewed-cid", file="config.json"), ["config.json"])
        self.assertTrue(self.publish()["reused"])
        self.assertEqual(self.renew()["sequence"], "10")

        # The node, not the CLI, must refuse rollback and misdirected records
        # even when they carry the owner's genuine signature.
        result = subprocess.run([os.environ.get("MODELSWARM_NODE", "node"), "--input-type=module", "-e", ANCHOR_ATTEMPTS],
                                cwd=BRIDGE.parent, input=json.dumps({"rpc": self.fixture["rpc_url"], "replay": "5",
                                    "privateKey": json.loads(self.key.read_text())["privateKey"]}),
                                capture_output=True, text=True, env=self.environment, timeout=60)
        self.assert_no_secrets(result.stdout + result.stderr)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout), {"sequence": "10", "outcome": {
            "replayed": "ERR_ANCHOR_IPNS_RECORD_SEQUENCE_IS_NOT_GREATER",
            "equal": "ERR_ANCHOR_IPNS_RECORD_SEQUENCE_IS_NOT_GREATER",
            "foreignMinter": "ERR_ANCHOR_IPNS_RECORD_POINTS_TO_DIFFERENT_MINTER",
            "foreignSigner": "ERR_ANCHOR_IPNS_RECORD_IS_INVALID"}})
        self.assertEqual(self.profile_state(), self.state("10"))

        other_key = self.root / "other.key.json"
        self.command("keygen", "-o", other_key)
        self.secrets.append(json.loads(other_key.read_text())["privateKey"])
        refused = self.renew(ok=False, key=other_key)
        self.assertIn("does not host", refused["error"])
        # The owner names the minter; a node presenting another one gets no signature.
        refused = self.renew(ok=False, minter=self.publisher)
        self.assertIn("different minter", refused["error"])
        self.assertEqual(self.profile_state(), self.state("10"))
        refused = self.command("profile-init", "--key", self.key, *self.rpc_options(), ok=False)
        self.assertIn("anchor record", refused["error"].lower())

    def test_renewed_delegation_survives_restart_and_renews_again(self):
        first = self.publish()
        self.assertEqual(self.renew()["sequence"], "5")
        self.assertEqual(self.restart(abrupt=False), self.state("5"))
        renewed = self.renew()
        self.assertEqual((renewed["previous_sequence"], renewed["sequence"]), ("5", "10"))
        self.assertEqual(self.restart(abrupt=True), self.state("10"))
        by_version = self.pull(first["release_uri"].split("#")[0], cache="restarted", file="config.json")
        self.assertEqual(by_version["release_cid"], first["release_cid"])
        second_manifest = self.root / "release-2.json"
        self.make(second_manifest, version="release-2")
        second = self.publish(manifest=second_manifest)
        self.assert_snapshot(self.pull(second["release_uri"], cache="restarted-fresh", file="config.json"),
                             ["config.json"])


if __name__ == "__main__":
    unittest.main()
