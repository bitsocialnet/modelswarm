"""Real CLI publication and discovery through a private PKC profile minter."""

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import select
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from urllib.request import Request, urlopen

from modelswarm.releases import BRIDGE, bridge
from pkc_fixture import pkc_fixture
from test_cli import gguf, http_source


def required_kubo():
    kubo = os.environ.get("MODELSWARM_KUBO_BIN") or shutil.which("ipfs")
    if not kubo:
        raise unittest.SkipTest("real PKC E2E requires Kubo 0.43.1; set MODELSWARM_KUBO_BIN")
    version = subprocess.run([kubo, "version", "--number"], capture_output=True, text=True, timeout=5)
    if version.returncode or version.stdout.strip() != "0.43.1":
        raise unittest.SkipTest("real PKC E2E requires Kubo 0.43.1; set MODELSWARM_KUBO_BIN")
    return kubo


class ReleaseCommands:
    """Real CLI subprocess helpers shared by suites that own a PKC fixture.

    Users set ``self.fixture`` to the node's current readiness record.
    """

    def prepare_workspace(self, parent):
        temporary = tempfile.TemporaryDirectory(prefix="release-", dir=parent)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.source = self.root / "source"
        self.source.mkdir()
        gguf(self.source / "weights.gguf", 64 * 1024 + 17)
        (self.source / "config.json").write_text('{"fixture":true}')
        (self.source / "empty.txt").write_bytes(b"")
        (self.source / "nested").mkdir()
        (self.source / "nested" / "readme.txt").write_text("Signed release fixture.\n")
        (self.source / "custom.py").write_text("raise RuntimeError('must never execute')\n")
        source_context = http_source(self.root)
        self.url, self.requests = source_context.__enter__()
        self.addCleanup(source_context.__exit__, None, None, None)
        self.environment = {key: value for key, value in os.environ.items()
                            if not key.startswith("HF_") and key not in {
                                "HUGGING_FACE_HUB_TOKEN", "HUGGINGFACE_HUB_CACHE", "DEBUG", "NODE_OPTIONS"}}
        self.environment.update({"NODE_DISABLE_COMPILE_CACHE": "1", "HF_HOME": str(self.root / "hf-home"),
                                 "HF_HUB_DISABLE_IMPLICIT_TOKEN": "1", "HF_HUB_DISABLE_PROGRESS_BARS": "1",
                                 "HF_HUB_DISABLE_TELEMETRY": "1", "HF_HUB_DOWNLOAD_TIMEOUT": "60"})
        self.secrets = []

    def create_profile(self):
        self.key = self.root / "publisher.key.json"
        generated = self.command("keygen", "-o", self.key)
        self.publisher = generated["publisher"]
        self.secrets.append(json.loads(self.key.read_text())["privateKey"])
        self.assertEqual(stat.S_IMODE(self.key.stat().st_mode), 0o600)
        initialized = self.command("profile-init", "--key", self.key, *self.rpc_options())
        self.assertTrue(initialized["started"])
        self.assertEqual(initialized["publisher"], self.publisher)
        self.assertNotEqual(initialized["minter"], self.publisher)
        self.minter = initialized["minter"]
        self.manifest = self.root / "release.json"
        self.make(self.manifest)

    def assert_no_secrets(self, value):
        # The RPC capability changes whenever the node restarts.
        for secret in [self.fixture["rpc_url"].rsplit("/", 1)[1], *self.secrets]:
            self.assertFalse(secret in value, "output leaked a private signing key or RPC credential")
        self.assertFalse('"privateKey"' in value, "output exposed a private signing key field")

    def command(self, *arguments, ok=True):
        result = subprocess.run([sys.executable, "-m", "modelswarm", *map(str, arguments)],
                                capture_output=True, text=True, env=self.environment, timeout=80)
        self.assert_no_secrets(result.stdout + result.stderr)
        if ok is not None:  # None: the caller inspects either outcome.
            self.assertEqual(result.returncode == 0, ok, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def rpc_options(self):
        return ["--rpc", self.fixture["rpc_url"], "--rpc-timeout", "60"]

    def make(self, path, *, name="fixture/model", version="release-1"):
        return self.command("make", self.source, "-o", path, "--name", name, "--version", version,
                            "--license", "apache-2.0", "--http-base", self.url + "source/")

    def publish(self, *, manifest=None, manifest_url=None, allow_local=True, ok=True, card=None):
        manifest = manifest or self.manifest
        options = ["--allow-local-sources"] if allow_local else []
        if card:
            options.extend(["--card", str(card)])
        return self.command("publish", manifest, "--key", self.key,
                            "--manifest-url", manifest_url or self.url + manifest.name,
                            *self.rpc_options(), *options, ok=ok)

    def pull(self, uri, *, cache="cache", allow_local=True, ok=True, file=None):
        options = ["--allow-local-sources"] if allow_local else []
        if file:
            options.extend(["--file", file])
        return self.command("pull", uri, *self.rpc_options(), *options, "--no-discovery",
                            "--cache-dir", self.root / cache, "--timeout", "15", ok=ok)

    def ipfs_add(self, path):
        """Pin a file in the current node's Kubo and return its ipfs:// URL."""
        boundary = "modelswarm-private-ipfs-fixture"
        data = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"release.json\"\r\n"
                "Content-Type: application/json\r\n\r\n").encode()
        data += path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
        request = Request(self.fixture["kubo_api"] + "/add?pin=true&progress=false&cid-version=0&raw-leaves=false",
                          data=data, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        with urlopen(request, timeout=10) as response:
            return "ipfs://" + json.loads(response.read())["Hash"]

    def assert_snapshot(self, result, expected):
        self.assertTrue(result["signed"])
        self.assertEqual(result["publisher"], self.publisher)
        snapshot = Path(result["snapshot"])
        self.assertEqual({file.relative_to(snapshot).as_posix() for file in snapshot.rglob("*") if file.is_file()},
                         set(expected))
        for name in expected:
            self.assertEqual(hashlib.sha256((snapshot / name).read_bytes()).hexdigest(),
                             hashlib.sha256((self.source / name).read_bytes()).hexdigest())

    def model_requests(self):
        return [request for request in self.requests if request["file"].startswith("source/")]


class ReleaseTests(ReleaseCommands, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        context = pkc_fixture(kubo_bin=required_kubo(), node_bin=os.environ.get("MODELSWARM_NODE"))
        cls.fixture = context.__enter__()
        cls.addClassCleanup(context.__exit__, None, None, None)

    def setUp(self):
        self.prepare_workspace(Path(self.fixture["data_dir"]).parent)
        self.create_profile()

    def test_profile_persists_and_version_and_cid_pulls_verify_bytes(self):
        card = self.root / "card.md"
        card.write_text("# Fixture\nA signed model card.\n")
        published = self.publish(card=card)
        self.assertTrue(published["signed"])
        self.assertEqual(published["publisher"], self.publisher)
        self.assertIn("#" + published["release_cid"], published["release_uri"])
        # profile-init and publish ran in separate processes that have exited.
        by_version = self.pull(published["release_uri"].split("#")[0], file="nested/readme.txt")
        self.assert_snapshot(by_version, ["nested/readme.txt"])
        by_cid = self.pull(published["release_uri"], cache="pinned-cache")
        self.assert_snapshot(by_cid, ["config.json", "weights.gguf", "nested/readme.txt", "empty.txt"])
        self.assertEqual(by_cid["release_cid"], published["release_cid"])
        self.assertNotIn("source/custom.py", {request["file"] for request in self.requests})

    def test_publisher_retry_is_idempotent_and_version_is_immutable(self):
        first = self.publish()
        retried = self.publish()
        self.assertTrue(retried["reused"])
        self.assertEqual(retried["release_cid"], first["release_cid"])
        (self.source / "config.json").write_text('{"fixture":"changed"}')
        replacement = self.root / "replacement.json"
        self.make(replacement)
        refused = self.publish(manifest=replacement, ok=False)
        self.assertIn("version", refused["error"].lower())
        self.assertEqual(self.model_requests(), [])

    def test_repeated_profile_init_cannot_replace_the_delegation(self):
        refused = self.command("profile-init", "--key", self.key, *self.rpc_options(), ok=False)
        self.assertIn("anchor record", refused["error"].lower())
        script = """
import PKC from '@pkcprotocol/pkc-js';
let input=''; for await(const chunk of process.stdin)input+=chunk;
const request=JSON.parse(input);
const pkc=await PKC({noData:true,pkcRpcClientsOptions:[request.rpc],kuboRpcClientsOptions:[],
  pubsubKuboRpcClientsOptions:[],httpRoutersOptions:[],ipfsGatewayUrls:[],resolveAuthorNames:false});
try {
  const profile=await pkc.createCommunity({publicKey:request.publisher});
  console.log(JSON.stringify({minter:profile.signer.address,anchor:profile.anchor.publicKey}));
} finally { await pkc.destroy(); }
"""
        result = subprocess.run([os.environ.get("MODELSWARM_NODE", "node"), "--input-type=module", "-e", script],
                                cwd=BRIDGE.parent, input=json.dumps({"rpc": self.fixture["rpc_url"],
                                                                   "publisher": self.publisher}),
                                capture_output=True, text=True, env=self.environment, timeout=30)
        self.assert_no_secrets(result.stdout + result.stderr)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout), {"minter": self.minter, "anchor": self.publisher})
        published = self.publish()
        downloaded = self.pull(published["release_uri"], file="config.json")
        self.assert_snapshot(downloaded, ["config.json"])

    def test_ipfs_manifest_roundtrip_uses_its_content_address(self):
        published = self.publish(manifest_url=self.ipfs_add(self.manifest))
        self.assertEqual(self.requests, [], "IPFS manifest publication must not fetch the HTTP manifest")
        downloaded = self.pull(published["release_uri"], file="nested/readme.txt")
        self.assert_snapshot(downloaded, ["nested/readme.txt"])
        self.assertEqual({request["file"] for request in self.requests}, {"source/nested/readme.txt"})

    def test_conflicting_owner_announcements_on_later_page_require_pinning(self):
        release = {"schema": "modelswarm/release/v0", "name": "fixture/model", "version": "release-1",
                   "manifest": {"url": self.url + self.manifest.name,
                                "sha256": hashlib.sha256(self.manifest.read_bytes()).hexdigest()},
                   "modelCard": ""}
        # Bypass Modelswarm's duplicate-version preflight using the actual SDK.
        # Two comments suffice: a large, valid profile description leaves room
        # for one preloaded announcement, putting the conflict on the next page.
        script = """
import assert from 'node:assert/strict';
import PKC from '@pkcprotocol/pkc-js';
let input=''; for await (const chunk of process.stdin) input+=chunk;
const request=JSON.parse(input);
const pkc=await PKC({noData:true,pkcRpcClientsOptions:[request.rpc],kuboRpcClientsOptions:[],
  pubsubKuboRpcClientsOptions:[],httpRoutersOptions:[],ipfsGatewayUrls:[],resolveAuthorNames:false});
const comments=[]; let profile;
async function waitFor(predicate) {
  const deadline=Date.now()+20000;
  while(!predicate()) { if(Date.now()>deadline)throw new Error('profile pagination did not become ready');
    await new Promise(resolve=>setTimeout(resolve,100)); }
}
try {
  const signer=await pkc.createSigner({type:'ed25519',privateKey:request.privateKey});
  profile=await pkc.createCommunity({publicKey:signer.address});
  profile.on('error',()=>{});
  await profile.update();
  await waitFor(()=>typeof profile.updatedAt==='number');
  await profile.edit({description:'P'.repeat(1024*1024-32*1024)});
  for(const marker of ['first','second']) {
    const release={...request.release,modelCard:marker+'x'.repeat(20*1024)};
    const comment=await pkc.createComment({communityPublicKey:signer.address,signer,
      title:'Conflicting fixture announcement '+marker,content:JSON.stringify(release)});
    comments.push(comment);
    const verified=new Promise((resolve,reject)=>{
      comment.once('challengeverification',resolve);comment.once('error',reject);
    });
    await comment.publish();
    assert.equal((await verified).challengeSuccess,true);
    assert.ok(comment.cid);
  }
  await waitFor(()=>profile.posts?.pages?.new?.comments?.length===1 && profile.posts.pages.new.nextCid);
  const first=profile.posts.pages.new;
  const later=await profile.posts.getPage({cid:first.nextCid});
  const cids=comments.map(comment=>comment.cid);
  assert.notEqual(cids[0],cids[1]);
  assert.equal(first.comments.filter(comment=>cids.includes(comment.cid)).length,1);
  assert.equal(later.comments.filter(comment=>cids.includes(comment.cid)).length,1);
  console.log(JSON.stringify({cids,minter:profile.signer.address,laterPage:first.nextCid}));
} finally {
  for(const comment of comments)await comment.stop();
  if(profile)await profile.stopWithoutRpcCall();
  await pkc.destroy();
}
"""
        result = subprocess.run([os.environ.get("MODELSWARM_NODE", "node"), "--input-type=module", "-e", script],
                                cwd=BRIDGE.parent, input=json.dumps({"rpc": self.fixture["rpc_url"],
                                    "privateKey": json.loads(self.key.read_text())["privateKey"], "release": release}),
                                capture_output=True, text=True, env=self.environment, timeout=60)
        self.assert_no_secrets(result.stdout + result.stderr)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        published = json.loads(result.stdout)
        self.assertEqual(published["minter"], self.minter)
        uri = f"pkc://{self.publisher}/fixture/model@release-1"
        refused = self.pull(uri, ok=False)
        self.assertIn("conflicting", refused["error"].lower())
        self.assertEqual(self.model_requests(), [])
        for index, cid in enumerate(published["cids"]):
            pinned = self.pull(uri + "#" + cid, cache=f"pinned-{index}", file="config.json")
            self.assert_snapshot(pinned, ["config.json"])
            self.assertEqual(pinned["release_cid"], cid)

    def test_wrong_publisher_and_pinned_cid_selector_are_rejected(self):
        published = self.publish()
        other_key = self.root / "other.key.json"
        other = self.command("keygen", "-o", other_key)
        self.secrets.append(json.loads(other_key.read_text())["privateKey"])
        wrong_publisher = published["release_uri"].replace(self.publisher, other["publisher"], 1)
        self.pull(wrong_publisher, ok=False)
        wrong_model = published["release_uri"].replace("/fixture/model@", "/fixture/other@")
        wrong_version = published["release_uri"].replace("@release-1#", "@release-2#")
        for selector in (wrong_model, wrong_version):
            with self.subTest(selector=selector):
                failed = self.pull(selector, ok=False)
                self.assertIn("match", failed["error"].lower())
        self.assertEqual(self.model_requests(), [])

    def test_manifest_tampering_is_rejected_before_download_then_restores(self):
        published = self.publish()
        original = self.manifest.read_bytes()
        changed = json.loads(original)
        changed["license"] = "tampered-license"
        self.manifest.write_text(json.dumps(changed))
        refused = self.pull(published["release_uri"], ok=False)
        self.assertIn("SHA-256", refused["error"])
        self.assertEqual(self.model_requests(), [])
        self.manifest.write_bytes(original)
        restored = self.pull(published["release_uri"], file="config.json")
        self.assert_snapshot(restored, ["config.json"])

    def test_validly_signed_announcement_cannot_rename_its_manifest(self):
        digest = hashlib.sha256(self.manifest.read_bytes()).hexdigest()
        # Deliberately bypass the CLI's pre-publication manifest consistency check
        # while retaining the real signer, PKC publication, and immutable CID.
        for name, version in (("fixture/wrong", "release-1"), ("fixture/model", "wrong-version")):
            with self.subTest(name=name, version=version):
                release = {"schema": "modelswarm/release/v0", "name": name, "version": version,
                           "manifest": {"url": self.url + self.manifest.name, "sha256": digest}, "modelCard": ""}
                published = bridge({"op": "publish", "rpc": self.fixture["rpc_url"],
                                    "privateKey": json.loads(self.key.read_text())["privateKey"], "release": release}, 60)
                uri = f"pkc://{self.publisher}/{name}@{version}#{published['cid']}"
                failed = self.pull(uri, ok=False)
                self.assertIn("name/version", failed["error"])
        self.assertEqual(self.model_requests(), [])

    def test_loopback_sources_require_explicit_opt_in(self):
        refused = self.publish(allow_local=False, ok=False)
        self.assertIn("allow-local-sources", refused["error"])
        published = self.publish()
        refused = self.pull(published["release_uri"], allow_local=False, ok=False)
        self.assertIn("allow-local-sources", refused["error"])
        self.assertEqual(self.model_requests(), [])

    @contextmanager
    def serve(self, release):
        logs = self.root / "endpoint.log"
        with logs.open("w") as stderr:
            process = subprocess.Popen([sys.executable, "-m", "modelswarm", "serve", "--release", release,
                                        *self.rpc_options(), "--allow-local-sources", "--no-upstream",
                                        "--no-discovery", "--cache-dir", str(self.root / "endpoint-cache"),
                                        "--host", "127.0.0.1", "--port", "0", "--timeout", "15"],
                                       stdout=subprocess.PIPE, stderr=stderr, text=True, env=self.environment)
            try:
                readable, _, _ = select.select([process.stdout], [], [], 70)
                self.assertTrue(readable, "signed endpoint did not announce readiness")
                line = process.stdout.readline()
                self.assertTrue(line, logs.read_text())
                self.assert_no_secrets(line + logs.read_text())
                ready = json.loads(line)
                self.assertEqual(ready.get("event"), "server_ready", line)
                yield ready["endpoint"]
            finally:
                if process.poll() is None:
                    process.terminate()
                try:
                    stdout, _ = process.communicate(timeout=20)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate(timeout=5)
                    self.fail("signed endpoint did not stop")
                self.assert_no_secrets(stdout + logs.read_text())
                self.assertEqual(process.returncode, 0, stdout + logs.read_text())

    def test_hugging_face_sdk_downloads_from_signed_release_endpoint(self):
        published = self.publish()
        with self.serve(published["release_uri"]) as endpoint:
            script = """
import hashlib,json
from pathlib import Path
from huggingface_hub import HfApi,snapshot_download
info = HfApi(token=False).model_info('fixture/model')
p = Path(snapshot_download('fixture/model', token=False, allow_patterns=['config.json','nested/*']))
print(json.dumps({'revision': info.sha, 'files': {
    f.relative_to(p).as_posix(): hashlib.sha256(f.read_bytes()).hexdigest()
    for f in p.rglob('*') if f.is_file()}}))
"""
            result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                                    env={**self.environment, "HF_ENDPOINT": endpoint,
                                         "HF_HUB_CACHE": str(self.root / "sdk-cache")}, timeout=80)
            self.assert_no_secrets(result.stdout + result.stderr)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            downloaded = json.loads(result.stdout)
            self.assertEqual(downloaded["revision"], published["manifest_sha256"][:40])
            self.assertEqual(set(downloaded["files"]), {"config.json", "nested/readme.txt"})
            for name, digest in downloaded["files"].items():
                self.assertEqual(digest, hashlib.sha256((self.source / name).read_bytes()).hexdigest())
            self.assertEqual({item["file"] for item in self.model_requests()},
                             {"source/config.json", "source/nested/readme.txt"})


if __name__ == "__main__":
    unittest.main()
