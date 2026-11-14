"""Manual run: a reader on another machine pulls from a publisher on this one.

Not part of the automatic suite (the name is outside unittest discovery): it
needs SSH access to a second machine prepared as cli/PERSISTENCE-EVALUATION.md
describes. The publisher node, its Kubo and a BitTorrent seeder run here and
listen on LOCAL_ADDRESS; the reader's own node and the CLI run on REMOTE.

    MODELSWARM_REMOTE=host MODELSWARM_REMOTE_DIR=modelswarm-xmachine \\
    MODELSWARM_LOCAL_ADDRESS=100.x.y.z [MODELSWARM_MODEL_FILE=/path/model.gguf] \\
      python -m unittest -v manual_cross_machine        # from cli/tests
"""

import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import time
import unittest

from test_cli import peers
from test_persistence import PersistentNode

REMOTE = os.environ.get("MODELSWARM_REMOTE")
REMOTE_DIR = os.environ.get("MODELSWARM_REMOTE_DIR", "modelswarm-xmachine")
LOCAL_ADDRESS = os.environ.get("MODELSWARM_LOCAL_ADDRESS")
MODEL_FILE = os.environ.get("MODELSWARM_MODEL_FILE")
REMOTE_PATH = "export PATH=$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH; "


def ssh(script, *, input=None, timeout=120, check=True):
    result = subprocess.run(["ssh", "-o", "BatchMode=yes", REMOTE, REMOTE_PATH + script], input=input,
                            capture_output=True, text=True, timeout=timeout)
    if check and result.returncode:
        raise RuntimeError(f"remote command failed: {result.stdout[-2000:]}{result.stderr[-2000:]}")
    return result


@unittest.skipUnless(REMOTE and LOCAL_ADDRESS, "set MODELSWARM_REMOTE and MODELSWARM_LOCAL_ADDRESS")
class CrossMachineTests(PersistentNode, unittest.TestCase):
    swarm_listen = f"/ip4/{LOCAL_ADDRESS}/tcp/0"

    def setUp(self):
        super().setUp()
        self.report = {"remote": REMOTE, "local_address": LOCAL_ADDRESS, "steps": []}
        self.run_dir = f"{REMOTE_DIR}/run-{os.getpid()}"
        remote = shlex.quote(self.run_dir)
        ssh(f"mkdir -m 700 {remote}")
        self.addCleanup(ssh, f"rm -rf {remote}", check=False)
        # The swarm key is the only thing the reader's node shares with the publisher's.
        ssh(f"umask 077; cat > {remote}/swarm.key", input=(self.node.data / "kubo" / "swarm.key").read_text())
        swarm = [address for address in self.fixture["swarm"] if LOCAL_ADDRESS in address]
        self.assertTrue(swarm, f"publisher Kubo does not listen on {LOCAL_ADDRESS}")
        command = (f"cd {shlex.quote(REMOTE_DIR)} && exec node cli/tests/pkc_fixture.mjs --kubo \"$(command -v ipfs)\""
                   f" --data-dir run-{os.getpid()}/reader --swarm-key run-{os.getpid()}/swarm.key"
                   f" --peer {shlex.quote(swarm[0])} 2>> run-{os.getpid()}/reader.log")
        self.reader_process = subprocess.Popen(["ssh", "-o", "BatchMode=yes", REMOTE, REMOTE_PATH + command],
                                               stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, text=True)
        self.addCleanup(self.stop_reader)
        self.reader = json.loads(self.reader_process.stdout.readline() or "{}")
        self.assertEqual(self.reader.get("event"), "pkc_fixture_ready", ssh(f"tail -c 2000 {remote}/reader.log").stdout)
        self.secrets.append(self.reader["rpc_url"].rsplit("/", 1)[1])

    def stop_reader(self):
        if self.reader_process.poll() is None and getattr(self, "reader", None):
            ssh(f"kill -TERM {int(self.reader['pid'])}", check=False)
        try:
            self.reader_process.communicate(timeout=40)
        except subprocess.TimeoutExpired:
            ssh(f"kill -KILL {int(self.reader['pid'])} {int(self.reader['kubo_pid'])}", check=False)
            self.reader_process.kill()
            self.reader_process.communicate()
            self.fail("remote reader node required forced cleanup")

    def remote_pull(self, uri, cache, *options, timeout=900):
        """Run the CLI on the remote machine against the remote node; hash what it stored."""
        arguments = " ".join(shlex.quote(str(value)) for value in ("pull", uri, "--cache-dir", f"run-{os.getpid()}/{cache}",
                                                                    "--no-discovery", "--rpc-timeout", "120", *options))
        # The RPC capability travels on stdin, never in a process listing.
        script = (f"cd {shlex.quote(REMOTE_DIR)} && read -r MODELSWARM_RPC && export MODELSWARM_RPC NODE_DISABLE_COMPILE_CACHE=1"
                  f" && cli/.venv/bin/modelswarm {arguments}")
        started = time.monotonic()
        result = ssh(script, input=self.reader["rpc_url"] + "\n", timeout=timeout, check=False)
        self.assert_no_secrets(result.stdout + result.stderr)
        pulled = json.loads(result.stdout.strip().splitlines()[-1])
        pulled["seconds"] = round(time.monotonic() - started, 1)
        if pulled.get("ok"):
            listing = ssh(f"cd {shlex.quote(pulled['snapshot'])} && find . -type f -o -type l | sort | while read -r f;"
                          " do printf '%s  %s\\n' \"$(shasum -a 256 \"$f\" | cut -d' ' -f1)\" \"${f#./}\"; done", timeout=300)
            pulled["sha256"] = dict(reversed(line.split("  ", 1)) for line in listing.stdout.splitlines())
        return pulled

    def remote_pull_when_discoverable(self, uri, cache, *options):
        deadline = time.monotonic() + 180
        while not (pulled := self.remote_pull(uri, cache, *options)).get("ok"):
            self.assertIn("No verified publisher release", pulled["error"])
            self.assertLess(time.monotonic(), deadline, "release never became discoverable on the remote node")
            time.sleep(2)
        return pulled

    def local_sha256(self, name):
        digest = hashlib.sha256()
        with (self.source / name).open("rb") as stream:
            while block := stream.read(1 << 20):
                digest.update(block)
        return digest.hexdigest()

    def record(self, step, **fields):
        self.report["steps"].append({"step": step, **fields})

    def test_remote_reader_pulls_verified_bytes_from_this_machine(self):
        files = ["weights.gguf", "nested/readme.txt"]
        if MODEL_FILE:
            shutil.copyfile(MODEL_FILE, self.source / Path(MODEL_FILE).name)
            files.append(Path(MODEL_FILE).name)
        manifest = self.root / "cross.json"
        self.command("make", self.source, "-o", manifest, "--name", "fixture/model", "--version", "cross-1",
                     "--license", "apache-2.0")
        published = self.publish(manifest=manifest, manifest_url=self.ipfs_add(manifest), allow_local=False)
        selection = [item for name in files for item in ("--file", name)]

        with peers(json.loads(manifest.read_text()), self.source, listen=LOCAL_ADDRESS) as (peer, handles):
            # Signed releases refuse non-public peers unless the reader opts in;
            # a tailnet or LAN address is such a peer.
            refused = self.remote_pull(published["release_uri"], "refused", "--peer", peer, "--timeout", "20", *selection)
            self.assertFalse(refused.get("ok"), refused)
            self.record("pull without --allow-local-sources", error=refused["error"], seconds=refused["seconds"])
            self.assertEqual(sum(handle.status().total_payload_upload for handle in handles), 0)

            by_cid = self.remote_pull(published["release_uri"], "by-cid", "--peer", peer, "--allow-local-sources",
                                      "--timeout", "600", *selection)
            self.assertTrue(by_cid.get("ok"), by_cid)
            uploaded = sum(handle.status().total_payload_upload for handle in handles)
            size = sum((self.source / name).stat().st_size for name in files)
            self.assertGreaterEqual(uploaded, size)
            self.assertEqual(by_cid["sha256"], {name: self.local_sha256(name) for name in files})
            self.assertEqual((by_cid["publisher"], by_cid["release_cid"], by_cid["signed"]),
                             (self.publisher, published["release_cid"], True))
            self.record("pinned CID pull", seconds=by_cid["seconds"], bytes=size, seeder_uploaded=uploaded, files=files)

            by_version = self.remote_pull_when_discoverable(published["release_uri"].split("#")[0], "by-version",
                                                            "--peer", peer, "--allow-local-sources", "--timeout", "120",
                                                            "--file", "nested/readme.txt")
            self.assertEqual(by_version["release_cid"], published["release_cid"])
            self.record("version discovery pull", seconds=by_version["seconds"])

            self.restart(abrupt=False)
            renewed = self.command("profile-renew", "--key", self.key, "--minter", self.minter, *self.rpc_options())
            second_manifest = self.root / "cross-2.json"
            self.command("make", self.source, "-o", second_manifest, "--name", "fixture/model", "--version", "cross-2",
                         "--license", "apache-2.0")
            second = self.publish(manifest=second_manifest, manifest_url=self.ipfs_add(second_manifest), allow_local=False)
            announced = time.monotonic()
            after = self.remote_pull_when_discoverable(second["release_uri"].split("#")[0], "after-restart", "--peer", peer,
                                                       "--allow-local-sources", "--timeout", "120", "--file", "nested/readme.txt")
            self.assertEqual(after["release_cid"], second["release_cid"])
            self.assertEqual(after["sha256"], {"nested/readme.txt": self.local_sha256("nested/readme.txt")})
            self.record("discovery after publisher restart and renewal", renewed_sequence=renewed["sequence"],
                        seconds_until_discovered=round(time.monotonic() - announced, 1))
        self.assertEqual(self.requests, [], "nothing may be fetched over HTTP")
        print(json.dumps(self.report, indent=2), file=sys.stderr)
        output = os.environ.get("MODELSWARM_REPORT")
        if output:
            Path(output).write_text(json.dumps(self.report, indent=2) + "\n")


if __name__ == "__main__":
    unittest.main()
