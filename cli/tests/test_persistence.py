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

    def setUp(self):
        artifacts = Path(__file__).resolve().parents[2] / ".tmp"
        artifacts.mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix="pkc-persist-", dir=artifacts)
        self.addCleanup(temporary.cleanup)
        directory = Path(temporary.name)
        self.node = FixtureNode(directory / "data", directory / "fixture.log", kubo_bin=required_kubo(),
                                node_bin=os.environ.get("MODELSWARM_NODE"))
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

    def restart(self, *, abrupt, settle=0):
        """Stop or SIGKILL the node, optionally wait, and resume it on the same data.

        pkc-js 0.0.142 leaves a killed node's start lock in place until it goes
        stale after 10 seconds, and its auto-start does not retry a held lock.
        ``settle`` waits that window out before restarting; a node restarted
        sooner needs ``profile-start`` once the lock is stale.
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
        time.sleep(settle)
        logged = len(self.node.log_path.read_text())
        self.fixture = self.node.start(resume=True)
        self.assertTrue(self.fixture["resumed"])
        self.assertEqual(self.fixture["data_dir"], previous["data_dir"])
        deadline = time.monotonic() + 60
        if abrupt and not settle:
            # Resumed well inside the stale window: the node must have refused
            # to host the profile, and says so through its RPC error event.
            while "ERR_COMMUNITY_ALREADY_STARTED" not in self.node.log_path.read_text()[logged:]:
                self.assertLess(time.monotonic(), deadline, "killed node did not report the held start lock")
                time.sleep(0.1)
            self.while_unhosted()
            while not (started := self.command("profile-start", self.publisher, *self.rpc_options(), ok=None)).get("ok"):
                self.assertIn("start lock", started["error"])
                self.assertLess(time.monotonic(), deadline, "killed node never released the profile start lock")
                time.sleep(1)
            self.assertEqual(started["minter"], self.minter)
            return self.profile_state()
        # The node must host the profile again by itself: no client asks it to.
        while not (state := self.profile_state())["started"]:
            self.assertLess(time.monotonic(), deadline, "restarted node did not resume hosting the profile")
            time.sleep(0.25)
        self.assertNotIn("ERR_COMMUNITY_ALREADY_STARTED", self.node.log_path.read_text()[logged:])
        return state

    def while_unhosted(self):
        """Hook: runs while a killed, immediately restarted node hosts nothing."""

    def pull_when_discoverable(self, uri, **options):
        """Version discovery of a release announced right after a restart.

        A restarted minter in pkc-js 0.0.142 resolves its own IPNS name before
        its first record; the isolated Kubo holds that lookup for 60 seconds.
        The announcement is accepted and CID-addressable at once, but joins the
        profile feed only with that delayed record.
        """
        deadline = time.monotonic() + 150
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
    def check_restart(self, *, abrupt, settle=0):
        first = self.published = self.publish()
        by_version = self.pull(first["release_uri"].split("#")[0], cache="before", file="config.json")
        self.assertEqual(by_version["release_cid"], first["release_cid"])
        before = self.profile_state()
        self.assertEqual(before, {"minter": self.minter, "anchor": self.publisher, "sequence": "0", "started": True})

        after = self.restart(abrupt=abrupt, settle=settle)
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

    def test_killed_node_restarted_after_lock_expiry_resumes_by_itself(self):
        self.check_restart(abrupt=True, settle=11)

    def test_immediately_restarted_killed_node_recovers_with_profile_start(self):
        unhosted = []

        def while_unhosted():
            # Nothing is lost: existing releases stay readable, new ones are refused.
            uri = self.published["release_uri"]
            pinned = self.pull(uri, cache=f"unhosted-cid-{len(unhosted)}", file="config.json")
            by_version = self.pull(uri.split("#")[0], cache=f"unhosted-version-{len(unhosted)}", file="config.json")
            self.assertEqual((pinned["release_cid"], by_version["release_cid"]), (self.published["release_cid"],) * 2)
            manifest = self.root / f"unhosted-{len(unhosted)}.json"
            self.make(manifest, version=f"unhosted-{len(unhosted)}")
            refused = self.publish(manifest=manifest, ok=False)
            self.assertIn("ERR_COMMUNITY_CHALLENGE_EXCHANGE_DISABLED", refused["error"])
            unhosted.append(refused)

        self.while_unhosted = while_unhosted
        first, second = self.check_restart(abrupt=True)
        self.published = second
        # A second crash, immediately after the post-recovery publication.
        self.restart(abrupt=True)
        for published in (first, second):
            pulled = self.pull(published["release_uri"].split("#")[0],
                               cache="twice-" + published["release_cid"][-8:], file="config.json")
            self.assert_snapshot(pulled, ["config.json"])
            self.assertEqual(pulled["release_cid"], published["release_cid"])
        self.assertEqual(len(unhosted), 2)

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
        self.assertEqual(self.restart(abrupt=True, settle=11), self.state("10"))
        by_version = self.pull(first["release_uri"].split("#")[0], cache="restarted", file="config.json")
        self.assertEqual(by_version["release_cid"], first["release_cid"])
        second_manifest = self.root / "release-2.json"
        self.make(second_manifest, version="release-2")
        second = self.publish(manifest=second_manifest)
        self.assert_snapshot(self.pull(second["release_uri"], cache="restarted-fresh", file="config.json"),
                             ["config.json"])


if __name__ == "__main__":
    unittest.main()
