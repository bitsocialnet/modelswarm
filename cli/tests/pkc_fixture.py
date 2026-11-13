"""Start the private PKC fixture and reap every process before removing its repo."""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import tempfile


@contextmanager
def pkc_fixture(*, kubo_bin=None, node_bin=None):
    root = Path(__file__).resolve().parents[2]
    artifacts = root / ".tmp"
    artifacts.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="pkc-e2e-", dir=artifacts) as temporary:
        directory = Path(temporary)
        data = directory / "data"
        args = [node_bin or os.environ.get("MODELSWARM_NODE_BIN", "node"),
                str(Path(__file__).with_suffix(".mjs")), "--data-dir", str(data)]
        if kubo_bin:
            args.extend(["--kubo", str(kubo_bin)])
        with (directory / "fixture.log").open("w+") as logs:
            process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=logs, text=True,
                                       start_new_session=True)
            try:
                readable, _, _ = select.select([process.stdout], [], [], 60)
                if not readable:
                    raise TimeoutError("PKC fixture did not announce readiness")
                line = process.stdout.readline()
                if not line:
                    logs.seek(0)
                    raise RuntimeError("PKC fixture failed: " + logs.read())
                ready = json.loads(line)
                if ready.get("event") != "pkc_fixture_ready":
                    raise RuntimeError("Unexpected PKC fixture readiness event")
                yield ready
            finally:
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
                    logs.seek(0)
                    raise RuntimeError("PKC fixture exited unsuccessfully: " + logs.read())
