"""Start the private PKC fixture and reap every process before removing its repo."""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import tempfile


class FixtureNode:
    """One fixture process over a data directory that outlives it.

    The caller owns the directory, so the same node can be stopped or killed
    and then resumed with its Kubo identity, PKC database and minter keys.
    """

    def __init__(self, data, log_path, *, kubo_bin=None, node_bin=None, swarm_key=None, peers=(), swarm_listen=None):
        self.data = Path(data)
        self.log_path = Path(log_path)
        self.kubo_bin = kubo_bin
        self.node_bin = node_bin or os.environ.get("MODELSWARM_NODE_BIN", "node")
        # Join another fixture's private swarm; applied when the repo is created.
        self.join = [item for peer in peers for item in ("--peer", peer)]
        if swarm_key:
            self.join += ["--swarm-key", str(swarm_key)]
        if swarm_listen:
            self.join += ["--swarm-listen", swarm_listen]
        self.process = None
        self.logs = None

    def start(self, *, resume=False):
        if self.process is not None:
            raise RuntimeError("PKC fixture is already running")
        args = [self.node_bin, str(Path(__file__).with_suffix(".mjs")), "--data-dir", str(self.data)]
        args.extend(["--resume"] if resume else self.join)
        if self.kubo_bin:
            args.extend(["--kubo", str(self.kubo_bin)])
        self.logs = self.log_path.open("a+")
        try:
            self.process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=self.logs, text=True,
                                            start_new_session=True)
        except BaseException:
            self.logs.close()
            self.logs = None
            raise
        try:
            readable, _, _ = select.select([self.process.stdout], [], [], 60)
            if not readable:
                raise TimeoutError("PKC fixture did not announce readiness")
            line = self.process.stdout.readline()
            if not line:
                raise RuntimeError("PKC fixture failed: " + self.read_logs())
            ready = json.loads(line)
            if ready.get("event") != "pkc_fixture_ready":
                raise RuntimeError("Unexpected PKC fixture readiness event")
            return ready
        except BaseException:
            self.kill()
            raise

    def read_logs(self):
        self.logs.seek(0)
        return self.logs.read()

    def _finish(self):
        self.process.stdout.close()
        self.logs.close()
        self.process = self.logs = None

    def stop(self):
        """Graceful SIGTERM shutdown; raises if any process needed force."""
        if self.process is None:
            return
        process = self.process
        try:
            if process.poll() is None:
                process.terminate()
            try:
                process.communicate(timeout=25)
            except subprocess.TimeoutExpired:
                # The group contains only this fixture and its Kubo child.
                os.killpg(process.pid, signal.SIGKILL)
                process.communicate(timeout=5)
                raise RuntimeError("PKC fixture required forced process-group cleanup")
            if process.returncode:
                # Covers a supervisor killed unexpectedly before it reaped
                # Kubo, as well as normal startup failures with no children.
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                raise RuntimeError("PKC fixture exited unsuccessfully: " + self.read_logs())
        finally:
            self._finish()

    def kill(self):
        """Abrupt SIGKILL of the fixture and its Kubo child: no cleanup runs."""
        if self.process is None:
            return
        process = self.process
        try:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.communicate(timeout=10)
        finally:
            self._finish()


@contextmanager
def pkc_fixture(*, kubo_bin=None, node_bin=None):
    root = Path(__file__).resolve().parents[2]
    artifacts = root / ".tmp"
    artifacts.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="pkc-e2e-", dir=artifacts) as temporary:
        directory = Path(temporary)
        node = FixtureNode(directory / "data", directory / "fixture.log", kubo_bin=kubo_bin, node_bin=node_bin)
        ready = node.start()
        try:
            yield ready
        finally:
            node.stop()
