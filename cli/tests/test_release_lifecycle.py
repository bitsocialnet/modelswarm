"""Real Python/Node process cleanup while a local RPC handshake is stalled."""

import base64
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
import unittest

from modelswarm.releases import BRIDGE


CHILD_SCRIPT = """
import json
from pathlib import Path
import signal
import sys
import modelswarm.releases as releases

request = json.load(sys.stdin)
previous = signal.getsignal(signal.SIGTERM)
original_popen = releases.subprocess.Popen
def record_child(*args, **kwargs):
    process = original_popen(*args, **kwargs)
    Path(sys.argv[1]).write_text(str(process.pid))
    return process
releases.subprocess.Popen = record_child
try:
    releases.bridge(request, timeout=60)
except BaseException as error:
    print(json.dumps({'error': str(error), 'handler_restored': signal.getsignal(signal.SIGTERM) == previous}), flush=True)
    sys.exit(1)
raise SystemExit('unexpected completed RPC request')
"""


@contextmanager
def stalled_rpc():
    stopped = threading.Event()
    received = threading.Event()

    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            self.request.settimeout(0.1)
            while not stopped.is_set():
                try:
                    data = self.request.recv(4096)
                    if not data:
                        return
                    # The real Node bridge has sent its WebSocket upgrade request;
                    # deliberately never answer, leaving the operation in flight.
                    received.set()
                except socket.timeout:
                    continue
                except (ConnectionResetError, OSError):
                    return

    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = False
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    try:
        yield f"ws://127.0.0.1:{server.server_address[1]}/lifecycle-token-sentinel", received
    finally:
        stopped.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def process_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


@unittest.skipUnless(os.name == "posix", "SIGTERM process-group behavior requires POSIX")
class ReleaseBridgeLifecycleTests(unittest.TestCase):
    def test_sigterm_kills_detached_bridge_restores_handler_and_keeps_secrets_private(self):
        node = os.environ.get("MODELSWARM_NODE") or shutil.which("node")
        if not node or not (BRIDGE.parent / "node_modules" / "@pkcprotocol" / "pkc-js").exists():
            self.skipTest("installed Node and PKC bridge dependencies are required")
        private_key = base64.b64encode(bytes(range(32))).decode().rstrip("=")
        with tempfile.TemporaryDirectory() as directory, stalled_rpc() as (rpc, received):
            pid_path = Path(directory) / "bridge.pid"
            request = {"op": "profile-init", "rpc": rpc, "privateKey": private_key}
            process = subprocess.Popen(
                [sys.executable, "-c", CHILD_SCRIPT, str(pid_path)],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, start_new_session=True,
            )
            bridge_pid = None
            try:
                process.stdin.write(json.dumps(request))
                process.stdin.close()
                process.stdin = None
                self.assertTrue(received.wait(10), "real Node bridge did not reach the stalled local RPC")
                self.assertTrue(pid_path.exists(), "bridge child PID was not recorded")
                bridge_pid = int(pid_path.read_text())
                self.assertNotEqual(bridge_pid, process.pid)
                self.assertTrue(process_alive(bridge_pid), "bridge exited before cancellation")
                self.assertIsNone(process.poll(), "Python exited before cancellation")

                process.send_signal(signal.SIGTERM)
                stdout, stderr = process.communicate(timeout=5)
                deadline = time.monotonic() + 3
                while process_alive(bridge_pid) and time.monotonic() < deadline:
                    time.sleep(0.025)
                self.assertFalse(process_alive(bridge_pid), "SIGTERM left the detached Node bridge running")
                self.assertEqual(process.returncode, 1, stdout + stderr)
                result = json.loads(stdout)
                self.assertIn("interrupted or timed out", result["error"])
                self.assertTrue(result["handler_restored"], "bridge leaked its temporary SIGTERM handler")
                for secret in (private_key, "privateKey", "lifecycle-token-sentinel"):
                    self.assertNotIn(secret, stdout + stderr)
            finally:
                # Failures must not leave the very orphan this test detects. Only
                # task-owned process groups whose PID we captured are signaled.
                if bridge_pid is None and pid_path.exists():
                    bridge_pid = int(pid_path.read_text())
                if bridge_pid is not None and process_alive(bridge_pid):
                    try:
                        os.killpg(bridge_pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGKILL)
                process.communicate(timeout=5)


if __name__ == "__main__":
    unittest.main()
