"""Exercise the CLI in subprocesses and inject filesystem failures in-process."""

import base64
from contextlib import contextmanager, redirect_stderr, redirect_stdout
import errno
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import re
import signal
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.parse import unquote, urlsplit

import libtorrent as lt

from modelswarm.cli import main, release_lock
from modelswarm.engine import MIB, session_settings
from modelswarm.view import PullView, width_of


def gguf(path, size):
    path.write_bytes(b"GGUF" + struct.pack("<IQQ", 3, 0, 0)
                     + hashlib.shake_256(path.name.encode()).digest(size - 24))


@contextmanager
def http_source(root, *, corrupt=False, delay=0):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            path = (root / unquote(urlsplit(self.path).path).lstrip("/")).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                self.send_error(404)
                return
            size = path.stat().st_size
            start, end = 0, size - 1
            value = self.headers.get("Range")
            if value:
                match = re.fullmatch(r"bytes=(\d+)-(\d*)", value)
                if not match:
                    self.send_error(416)
                    return
                start = int(match[1])
                end = min(int(match[2]) if match[2] else end, end)
                if start > end or start >= size:
                    self.send_error(416)
                    return
            self.send_response(206 if value else 200)
            self.send_header("Content-Length", str(end - start + 1))
            self.send_header("Accept-Ranges", "bytes")
            if value:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            sent = 0
            try:
                with path.open("rb") as source:
                    source.seek(start)
                    while sent < end - start + 1:
                        block = source.read(min(64 * 1024, end - start + 1 - sent))
                        if corrupt and sent == 0:
                            block = bytes([block[0] ^ 255]) + block[1:]
                        self.wfile.write(block)
                        sent += len(block)
                        if delay:
                            time.sleep(delay)
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                requests.append({"file": path.relative_to(root).as_posix(), "start": start, "end": end, "sent": sent})

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = False
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/", requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@contextmanager
def peers(manifest, source, listen="127.0.0.1", *, connections=None):
    settings = {**session_settings(False, 0), "listen_interfaces": f"{listen}:0"}
    if connections is not None:
        settings["alert_mask"] |= int(lt.alert.category_t.connect_notification)
    session = lt.session(settings)
    handles = []
    try:
        for entry in manifest["files"]:
            if entry["torrent"] is None:
                continue
            params = lt.add_torrent_params()
            params.ti = lt.torrent_info(base64.b64decode(entry["torrent"]["metadata"]))
            params.save_path = str((source / entry["path"]).parent)
            params.flags &= ~(lt.torrent_flags.paused | lt.torrent_flags.auto_managed)
            params.flags |= lt.torrent_flags.disable_dht | lt.torrent_flags.disable_lsd | lt.torrent_flags.disable_pex
            handles.append(session.add_torrent(params))
        deadline = time.monotonic() + 20
        while not all(handle.status().is_seeding for handle in handles):
            if time.monotonic() > deadline:
                raise TimeoutError("local seed did not become ready")
            time.sleep(0.02)
        yield f"{listen}:{session.listen_port()}", handles
    finally:
        if connections is not None:
            connections.extend(alert.endpoint for alert in session.pop_alerts()
                               if isinstance(alert, lt.peer_connect_alert))
        session.pause()
        for handle in handles:
            session.remove_torrent(handle)


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.source = self.root / "source"
        self.source.mkdir()
        gguf(self.source / "weights.gguf", 6 * MIB + 319)
        (self.source / "config.json").write_text('{"model_type":"fixture"}')
        (self.source / "README.md").write_text("Test model; no inference is run.\n")
        (self.source / "empty.txt").write_text("")
        nested = self.source / "shards"
        nested.mkdir()
        header = json.dumps({"tensor": {"dtype": "U8", "shape": [MIB + 123], "data_offsets": [0, MIB + 123]}}).encode()
        # The little-endian length starts with the pickle protocol 3 prefix.
        header = header.ljust(896, b" ")
        (nested / "part.safetensors").write_bytes(struct.pack("<Q", len(header)) + header + b"x" * (MIB + 123))
        (self.source / "custom.py").write_text("raise RuntimeError('must never execute')\n")
        self.manifest = self.root / "release.json"
        self.cache = self.root / "cache"

    def tearDown(self):
        self.temporary.cleanup()

    def command(self, *arguments, ok=True, timeout=45):
        result = subprocess.run([sys.executable, "-m", "modelswarm", *map(str, arguments)],
                                capture_output=True, text=True, timeout=timeout)
        self.assertEqual(result.returncode == 0, ok, result.stdout + result.stderr)
        return json.loads(result.stdout), result.stderr

    def make(self, *options):
        return self.command("make", self.source, "-o", self.manifest, "--name", "test/model",
                            "--version", "release-1", "--license", "apache-2.0", *options)[0]

    def pull(self, *options, ok=True):
        return self.command("pull", self.manifest, "--cache-dir", self.cache,
                            "--no-discovery", "--timeout", "20", *options, ok=ok)

    def test_release_lock_preserves_non_contention_io_failure(self):
        operation = "msvcrt.locking" if os.name == "nt" else "fcntl.flock"
        with patch(operation, side_effect=OSError(errno.EIO, os.strerror(errno.EIO))):
            with self.assertRaises(OSError) as raised, release_lock(self.root, "a" * 64):
                self.fail("release lock unexpectedly acquired")
        self.assertEqual(raised.exception.errno, errno.EIO)

    def test_make_verify_portability_and_mismatch(self):
        made = self.make()
        self.assertEqual(made["flagged"], ["custom.py"])
        verified, _ = self.command("verify", self.manifest, self.source)
        self.assertEqual(len(verified["verified"]), 6)
        second = self.root / "same.json"
        self.command("make", self.source, "-o", second, "--name", "test/model", "--version", "release-1", "--license", "apache-2.0")
        self.assertEqual(second.read_bytes(), self.manifest.read_bytes())
        original = self.manifest.read_bytes()
        self.command("make", self.source, "-o", self.manifest, "--name", "test/model", "--license", "apache-2.0", ok=False)
        self.assertEqual(original, self.manifest.read_bytes())
        (self.source / "config.json").write_text('{"model_type":"changed"}')
        bad, _ = self.command("verify", self.manifest, self.source, ok=False)
        self.assertEqual(bad["errors"][0]["path"], "config.json")

    def test_make_fails_before_publishing_on_traversal_error(self):
        blocked = self.source / "shards"
        scandir = os.scandir

        def scan(path):
            if Path(path) == blocked:
                raise PermissionError(errno.EACCES, os.strerror(errno.EACCES), path)
            return scandir(path)

        stdout, stderr = io.StringIO(), io.StringIO()
        with (patch("modelswarm.cli.os.scandir", side_effect=scan),
              redirect_stdout(stdout), redirect_stderr(stderr)):
            code = main(["make", str(self.source), "-o", str(self.manifest),
                         "--name", "test/model", "--license", "apache-2.0"])
        self.assertEqual(code, 1, stdout.getvalue())
        result = json.loads(stdout.getvalue())
        self.assertFalse(result["ok"])
        self.assertIn(str(blocked), result["error"])
        self.assertFalse(self.manifest.exists())

    def test_make_accepts_host_only_http_base(self):
        (self.source / "shards" / "labels #1.txt").write_text("labels\n")
        origin = "https://Files.example.com:8443"
        mirror = "https://mirror.example.com/model%20files/"
        self.make("--http-base", origin, "--http-base", mirror)
        paths = {entry["path"]: entry["sources"] for entry in json.loads(self.manifest.read_text())["files"]}
        self.assertEqual(paths["shards/labels #1.txt"], [
            {"type": "http", "url": origin + "/shards/labels%20%231.txt"},
            {"type": "http", "url": mirror + "shards/labels%20%231.txt"},
        ])

        second = self.root / "with-slash.json"
        self.command("make", self.source, "-o", second, "--name", "test/model",
                     "--version", "release-1", "--license", "apache-2.0",
                     "--http-base", origin + "/", "--http-base", mirror)
        self.assertEqual(second.read_bytes(), self.manifest.read_bytes())

    def test_make_rejects_invalid_http_bases(self):
        for index, (base, error) in enumerate((
            ("https://user@files.example.com", "without credentials"),
            ("https://files.exa\tmple.com", "unencoded whitespace"),
            (" https://files.example.com", "unencoded whitespace"),
            ("https://files.example.com ", "unencoded whitespace"),
            ("https://files.example.com#fragment", "fragment"),
            ("https://files.example.com/#", "fragment"),
            ("https://files.example.com?download=1", "query parameters"),
            ("https://files.example.com/?", "query parameters"),
        )):
            with self.subTest(base=base):
                output = self.root / f"invalid-{index}.json"
                result, _ = self.command("make", self.source, "-o", output,
                                         "--name", "test/model", "--license", "apache-2.0",
                                         "--http-base", base, ok=False)
                self.assertIn(error, result["error"])
                self.assertFalse(output.exists())

    def test_make_omits_huggingface_local_dir_cache(self):
        cache = self.source / ".cache"
        bookkeeping = cache / "huggingface"
        download = bookkeeping / "download" / "shards"
        download.mkdir(parents=True)
        (bookkeeping / ".gitignore").write_text("*")
        (bookkeeping / "CACHEDIR.TAG").write_text("Signature: 8a477f597d28d172789f06886806bc55\n")
        (download / "part.safetensors.lock").touch()
        metadata = download / "part.safetensors.metadata"
        metadata_prefix = f"{'a' * 40}\netag\n"
        metadata.write_text(metadata_prefix + "1\n")
        (download / "digest.etag.incomplete").write_bytes(b"partial data")
        (cache / "settings.json").write_text("{}")
        nested = self.source / "shards" / ".cache" / "huggingface"
        nested.mkdir(parents=True)
        (nested / "notes.txt").write_text("Model documentation\n")

        self.make()
        metadata.write_text(metadata_prefix + "2\n")
        second = self.root / "same.json"
        self.command("make", self.source, "-o", second, "--name", "test/model",
                     "--version", "release-1", "--license", "apache-2.0")

        self.assertEqual(second.read_bytes(), self.manifest.read_bytes())
        paths = {entry["path"] for entry in json.loads(self.manifest.read_text())["files"]}
        self.assertTrue({".cache/settings.json", "shards/.cache/huggingface/notes.txt",
                         "shards/part.safetensors"}.issubset(paths))
        self.assertFalse(any(path.startswith(".cache/huggingface/") for path in paths))

    def test_make_omits_root_checkout_metadata(self):
        (self.source / ".gitattributes").write_text("*.gguf filter=lfs\n")
        self.make()
        original = self.manifest.read_bytes()
        paths = {entry["path"] for entry in json.loads(original)["files"]}
        self.assertIn(".gitattributes", paths)
        for directory, filename in ((".git", "HEAD"), (".hg", "hgrc"), (".svn", "wc.db")):
            metadata = self.source / directory
            metadata.mkdir()
            (metadata / filename).write_text("checkout metadata\n")

        checkout = self.root / "checkout.json"
        self.command("make", self.source, "-o", checkout, "--name", "test/model",
                     "--version", "release-1", "--license", "apache-2.0")
        self.assertEqual(checkout.read_bytes(), original)

        (self.source / ".git").rename(self.root / "git-dir")
        (self.source / ".git").write_text("gitdir: ../git-dir\n")
        worktree = self.root / "worktree.json"
        self.command("make", self.source, "-o", worktree, "--name", "test/model",
                     "--version", "release-1", "--license", "apache-2.0")
        self.assertEqual(worktree.read_bytes(), original)

    def test_make_rejects_nested_git_metadata(self):
        metadata = self.source / "shards" / ".git"
        metadata.mkdir()
        (metadata / "HEAD").write_text("ref: refs/heads/main\n")
        result, _ = self.command("make", self.source, "-o", self.manifest, "--name", "test/model",
                                 "--license", "apache-2.0", ok=False)
        self.assertIn("unsafe or nonportable file path: 'shards/.git/HEAD'", result["error"])
        self.assertFalse(self.manifest.exists())

    def test_make_rejects_root_git_symlink(self):
        git_dir = self.root / "git-dir"
        git_dir.mkdir()
        (self.source / ".git").symlink_to(git_dir, target_is_directory=True)
        result, _ = self.command("make", self.source, "-o", self.manifest, "--name", "test/model",
                                 "--license", "apache-2.0", ok=False)
        self.assertIn("source symlinks are not supported: .git", result["error"])
        self.assertFalse(self.manifest.exists())

    def test_http_pull_safe_selection_cache_and_sdk(self):
        with http_source(self.source) as (url, requests):
            made = self.make("--http-base", url)
            pulled, _ = self.pull("--manifest-sha256", made["manifest_sha256"])
            snapshot = Path(pulled["snapshot"])
            self.assertEqual(pulled["skipped_flagged"], ["custom.py"])
            self.assertFalse((snapshot / "custom.py").exists())
            self.assertFalse(any(request["file"] == "custom.py" for request in requests))
            self.command("verify", self.manifest, snapshot, "--file", "weights.gguf", "--file", "shards/part.safetensors")
            full, _ = self.pull("--allow-unsafe")
            self.command("verify", self.manifest, full["snapshot"])
        # No HTTP server now: a repeat must use verified cache/staging only.
        repeated, logs = self.pull("--allow-unsafe")
        self.assertEqual(repeated["snapshot"], full["snapshot"])
        self.assertIn('"event": "file_cached"', logs)
        script = """import json,sys
from huggingface_hub import snapshot_download,hf_hub_download
cache,revision=sys.argv[1:]
snapshot=snapshot_download('test/model',cache_dir=cache,revision=revision,local_files_only=True)
file=hf_hub_download('test/model','shards/part.safetensors',cache_dir=cache,revision=revision,local_files_only=True)
print(json.dumps({'snapshot':snapshot,'file':file}))
"""
        environment = {**os.environ, "HF_HUB_OFFLINE": "1"}
        sdk = subprocess.run([sys.executable, "-c", script, str(self.cache), pulled["revision"]],
                             capture_output=True, text=True, env=environment, timeout=15)
        self.assertEqual(sdk.returncode, 0, sdk.stderr)
        self.assertEqual(json.loads(sdk.stdout)["snapshot"], pulled["snapshot"])

    def test_peer_only_multifile_pull(self):
        self.make()
        with peers(json.loads(self.manifest.read_text()), self.source) as (peer, handles):
            pulled, _ = self.pull("--peer", peer)
            self.assertGreater(sum(handle.status().total_payload_upload for handle in handles), 0)
            self.command("verify", self.manifest, pulled["snapshot"], "--file", "weights.gguf", "--file", "shards/part.safetensors")

    def test_periodic_checkpoint_keeps_the_peer_connection_open(self):
        gguf(self.source / "weights.gguf", 12 * MIB + 319)
        self.make()
        connections = []
        with peers(json.loads(self.manifest.read_text()), self.source, connections=connections) as (peer, _):
            pulled, logs = self.pull("--peer", peer, "--file", "weights.gguf",
                                     "--rate-limit", str(3 * MIB), "--checkpoint-interval", "1")
        checkpoints = [json.loads(line) for line in logs.splitlines() if line.startswith('{"event": "checkpoint_saved"')]
        self.assertGreaterEqual(sum(event["reason"] == "periodic" for event in checkpoints), 2, logs)
        self.assertEqual(len(connections), 1, logs)
        self.command("verify", self.manifest, pulled["snapshot"], "--file", "weights.gguf")

    def test_mixed_peer_and_http_pull(self):
        gguf(self.source / "weights.gguf", 32 * MIB + 319)
        with http_source(self.source, delay=0.01) as (url, requests):
            self.make("--http-base", url)
            with peers(json.loads(self.manifest.read_text()), self.source) as (peer, handles):
                result, _ = self.pull("--peer", peer, "--file", "weights.gguf")
                self.assertGreater(sum(handle.status().total_payload_upload for handle in handles), 0)
                self.assertGreater(sum(request["sent"] for request in requests), 0)
                self.command("verify", self.manifest, result["snapshot"], "--file", "weights.gguf")

    def test_corrupted_http_falls_back_and_never_publishes_bad_bytes(self):
        with http_source(self.source, corrupt=True) as (bad, _), http_source(self.source, delay=0.003) as (good, _):
            self.make("--http-base", bad, "--http-base", good)
            result, logs = self.pull("--file", "weights.gguf")
            self.assertIn('"event": "hash_failed"', logs)
            self.command("verify", self.manifest, result["snapshot"], "--file", "weights.gguf")

    def test_human_progress_names_bad_sources_and_keeps_json_result(self):
        with http_source(self.source, corrupt=True) as (bad, _), http_source(self.source, delay=0.003) as (good, _):
            self.make("--http-base", bad, "--http-base", good)
            result, logs = self.pull("--file", "weights.gguf", "--progress", "human")
        bad_name, good_name = (urlsplit(url).netloc for url in (bad, good))
        self.assertNotIn('{"event"', logs)
        self.assertIn("unsigned local file", logs)
        self.assertRegex(logs, rf"✗ piece #\d{{3}} from {re.escape(bad_name)} failed its hash check and was discarded")
        self.assertRegex(logs, rf"✓ piece #\d{{3}} fetched again from {re.escape(good_name)}")
        self.assertRegex(logs, rf"✓ weights\.gguf  6\.3 MB · 7 pieces · [\d.]+ s\n  from {re.escape(good_name)}\n")
        self.assertIn(f"snapshot   {result['snapshot']}", logs)
        self.command("verify", self.manifest, result["snapshot"], "--file", "weights.gguf")

    def test_json_progress_reports_piece_totals_without_piece_events(self):
        self.make()
        with peers(json.loads(self.manifest.read_text()), self.source) as (peer, _):
            _, logs = self.pull("--peer", peer, "--file", "weights.gguf", "--progress", "json")
        events = [json.loads(line) for line in logs.splitlines()]
        started = next(event for event in events if event["event"] == "file_started")
        self.assertEqual((started["total_pieces"], started["piece_size"]), (7, MIB))
        self.assertFalse(any(event["event"] == "piece_verified" for event in events))

    def test_manifest_digest_tampering_and_format_lie(self):
        with http_source(self.source) as (url, _):
            made = self.make("--http-base", url)
            self.pull("--manifest-sha256", "0" * 64, ok=False)
            self.assertFalse(self.cache.exists())
            value = json.loads(self.manifest.read_text())
            code = next(entry for entry in value["files"] if entry["path"] == "custom.py")
            code["format"] = "text"
            self.manifest.write_text(json.dumps(value))
            self.pull("--file", "custom.py", ok=False)
            self.assertFalse(self.cache.exists())
            weight = next(entry for entry in value["files"] if entry["path"] == "weights.gguf")
            weight["format"] = "text"
            self.manifest.write_text(json.dumps(value))
            result, _ = self.pull("--file", "weights.gguf", ok=False)
            self.assertIn("format mismatch", result["error"])
            self.assertFalse((self.cache / "models--test--model" / "snapshots").exists())

    def test_missing_source_times_out_without_snapshot(self):
        self.make("--http-base", "http://127.0.0.1:1/")
        result, _ = self.pull("--file", "weights.gguf", "--timeout", "0.4", ok=False)
        self.assertIn("timeout", result["error"])
        self.assertFalse((self.cache / "models--test--model" / "snapshots").exists())

    def test_nonfinite_timeouts_rejected_before_cache_creation(self):
        self.make()
        for value in ("nan", "inf", "-inf"):
            self.pull("--timeout=" + value, ok=False)
            self.assertFalse(self.cache.exists())

    def test_path_traversal_and_source_symlink_rejected(self):
        self.make()
        value = json.loads(self.manifest.read_text())
        value["files"][0]["path"] = "../escape"
        self.manifest.write_text(json.dumps(value))
        self.pull(ok=False)
        self.assertFalse(self.cache.exists())
        (self.source / "link.txt").symlink_to(self.root / "outside.txt")
        self.command("make", self.source, "-o", self.root / "new.json", "--name", "test/model", "--license", "apache-2.0", ok=False)

    def interrupt_and_resume(self, signum, corrupt_staged_piece=False):
        gguf(self.source / "weights.gguf", 32 * MIB + 319)
        with http_source(self.source, delay=0.002) as (url, _):
            self.make("--http-base", url)
            log = self.root / "interrupt.stderr"
            output = self.root / "interrupt.stdout"
            command = [sys.executable, "-m", "modelswarm", "pull", str(self.manifest), "--cache-dir", str(self.cache),
                       "--file", "weights.gguf", "--no-discovery", "--rate-limit", str(2 * MIB), "--timeout", "30"]
            if signum == signal.SIGKILL:
                command.extend(["--checkpoint-interval", "1"])
            with log.open("w") as stderr, output.open("w") as stdout:
                process = subprocess.Popen(command, stdout=stdout, stderr=stderr)
                try:
                    deadline = time.monotonic() + 20
                    while time.monotonic() < deadline:
                        event = "checkpoint_saved" if signum == signal.SIGKILL else "progress"
                        progress = [json.loads(line) for line in log.read_text().splitlines() if line.startswith('{"event": "' + event + '"')]
                        minimum = 3 if corrupt_staged_piece else 1
                        if any(event["verified_pieces"] >= minimum for event in progress):
                            break
                        self.assertIsNone(process.poll(), output.read_text() + log.read_text())
                        time.sleep(0.05)
                    else:
                        self.fail("partial verified progress not observed")
                    process.send_signal(signum)
                    process.wait(timeout=20)
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.wait(timeout=10)
            self.assertEqual(process.returncode, 130 if signum == signal.SIGINT else -signal.SIGKILL)
            self.assertFalse((self.cache / "models--test--model" / "snapshots").exists())
            if signum == signal.SIGINT:
                self.assertIn('"event": "checkpoint_saved"', log.read_text())
            if corrupt_staged_piece:
                checkpoint = next(self.cache.glob(".modelswarm/*/files/*/resume.data"))
                saved = lt.read_resume_data(checkpoint.read_bytes())
                piece = next(index for index, have in enumerate(saved.have_pieces) if have)
                payload = checkpoint.parent / "payload" / "weights.gguf"
                with payload.open("r+b") as stream:
                    stream.seek(piece * MIB)
                    byte = stream.read(1)
                    stream.seek(piece * MIB)
                    stream.write(bytes([byte[0] ^ 255]))
            resumed, logs = self.pull("--file", "weights.gguf")
            completions = [json.loads(line) for line in logs.splitlines() if line.startswith('{"event": "file_complete"')]
            checkpoints = [json.loads(line) for line in logs.splitlines() if line.startswith('{"event": "checkpoint_saved"')]
            # A fresh native session reports only bytes fetched by this pull.
            self.assertEqual([event["reason"] for event in checkpoints], ["complete"])
            self.assertLess(completions[0]["payload_bytes_since_resume"], 32 * MIB + 319)
            self.command("verify", self.manifest, resumed["snapshot"], "--file", "weights.gguf")

    def test_sigint_checkpoint_and_resume(self):
        self.interrupt_and_resume(signal.SIGINT)

    def test_changed_checkpointed_piece_is_rechecked_and_repaired(self):
        self.interrupt_and_resume(signal.SIGINT, corrupt_staged_piece=True)

    @unittest.skipUnless(hasattr(signal, "SIGKILL"), "requires SIGKILL")
    def test_sigkill_resume_after_periodic_checkpoint(self):
        self.interrupt_and_resume(signal.SIGKILL)


class TtyStream(io.StringIO):
    def isatty(self):
        return True


class PullViewTests(unittest.TestCase):
    def test_live_region_redraws_and_collapses_into_lasting_lines(self):
        stream = TtyStream()
        with patch.dict(os.environ, {"NO_COLOR": "1"}), patch("shutil.get_terminal_size", return_value=os.terminal_size((80, 40))):
            view = PullView(stream, live=True)
            view.start({"name": "example/model", "version": "v1", "license": "mit"}, "ab" * 32,
                       [{"path": "model.gguf", "size": 4 * MIB}], [], {"signed": True, "publisher": "12D3KooW" + "x" * 44}, False)
            view("file_started", path="model.gguf", size=4 * MIB, total_pieces=4, piece_size=MIB, pid=1)
            view("file_ready", path="model.gguf", verified_pieces=1, have=bytes([1, 0, 0, 0]))
            view("piece_verified", path="model.gguf", piece=1, source="peer 192.0.2.10:6881")
            view("hash_failed", path="model.gguf", piece=2, source="mirror.example.org")
            view("source_banned", path="model.gguf", source="mirror.example.org")
            view("progress", path="model.gguf", verified_pieces=2, total_pieces=4, payload_bytes_since_resume=MIB)
            live = stream.getvalue()
            view("piece_verified", path="model.gguf", piece=2, source="peer 192.0.2.10:6881")
            view("piece_verified", path="model.gguf", piece=3, source="huggingface.co")
            view("file_complete", path="model.gguf", size=4 * MIB, seconds=1.25, hash_failures=1)
            view.finish({"files": ["model.gguf"], "snapshot": "/cache/snapshots/abab"})
        self.assertNotRegex(stream.getvalue(), r"\x1b\[[\d;]*m")
        self.assertIn("publisher  12D3KooWxxxx…xxxx ✓ signature valid", live)
        self.assertRegex(live, r"╭─ model\.gguf · 4\.2 MB ─+ ✗ bad piece ─╮\n")
        # Without colour, glyphs alone tell verified, failed and missing pieces apart.
        self.assertRegex(live, r"│ ■ ■ × · +│\n")
        self.assertRegex(live, r"│ mirror\.example\.org +─+  dropped │\n")
        self.assertIn("2/4 verified", live)
        self.assertIn("\x1b[", live)
        lines = live.splitlines()
        self.assertEqual({len(line) for line in lines if line.startswith(("╭", "│", "╰"))}, {69})
        final = stream.getvalue().rsplit("\x1b[J", 1)[1]
        self.assertIn("✓ piece #002 fetched again from peer 192.0.2.10:6881\n", stream.getvalue())
        self.assertEqual(final.splitlines(), [
            "✓ model.gguf  4.2 MB · 4 pieces · 1.2 s",
            "  from peer 192.0.2.10:6881 (2), huggingface.co (1)",
            "",
            "verified   ✓ 1 file",
            "snapshot   /cache/snapshots/abab",
        ])
        self.assertEqual(view.drawn, 0)


    def live_lines(self, columns, rows, sources, path="model.gguf"):
        stream = TtyStream()
        with patch.dict(os.environ, {"NO_COLOR": "1"}), patch("shutil.get_terminal_size", return_value=os.terminal_size((columns, rows))):
            view = PullView(stream, live=True)
            view("file_started", path=path, size=64 * MIB, total_pieces=64, piece_size=MIB, pid=1)
            view("file_ready", path=path, verified_pieces=0, have=bytes(64))
            for piece, source in enumerate(sources):
                view("piece_verified", path=path, piece=piece, source=source)
            view("progress", path=path, payload_bytes_since_resume=MIB)
        return view, stream.getvalue().rsplit("\x1b[J", 1)[1].splitlines()

    def test_many_sources_fold_so_the_box_fits_the_terminal(self):
        sources = [f"peer 192.0.2.{n}:6881" for n in range(1, 11) for _ in range(n)]
        view, lines = self.live_lines(80, 24, sources)
        self.assertLessEqual(len(lines), 23)
        self.assertEqual(view.drawn, len(lines))
        rows = [line for line in lines if "─" in line and ("peer" in line or "more" in line)]
        # The four busiest peers stay, in arrival order; the other six fold into one row.
        self.assertEqual([row.split()[2] for row in rows[:4]], [f"192.0.2.{n}:6881" for n in (7, 8, 9, 10)])
        self.assertRegex(rows[4], r"│ \+6 more +[━╸─]+ +21 │")

    def test_tiny_terminal_clips_the_box_instead_of_overflowing(self):
        view, lines = self.live_lines(80, 10, ["peer 192.0.2.1:6881"])
        self.assertEqual(len(lines), 9)
        self.assertTrue(lines[-1].startswith("╰"))

    def test_wide_characters_keep_the_box_in_its_columns(self):
        view, lines = self.live_lines(80, 40, ["peer 192.0.2.1:6881", "模型.example.org"], path="模型" * 20 + ".gguf")
        box = [line for line in lines if line.startswith(("╭", "│", "╰"))]
        self.assertEqual({width_of(line) for line in box}, {69})
        self.assertRegex(box[0], r"^╭─ [模型]+… ─+ \S pulling ─╮$")
        self.assertTrue(any(line.startswith("│ 模型.example.org ") for line in box))

    def test_narrow_terminal_gets_a_status_line_instead_of_the_box(self):
        view, lines = self.live_lines(20, 24, ["peer 192.0.2.1:6881"])
        self.assertEqual(view.drawn, len(lines))
        self.assertEqual(len(lines), 1)
        self.assertLessEqual(width_of(lines[0]), 19)
        self.assertRegex(lines[0], r"^\S 1/64 verified")

    def test_source_counts_stay_visible_when_names_are_cut(self):
        view, lines = self.live_lines(38, 40, ["peer 159.195.210.230:51413"] * 3)
        self.assertIn("│ peer 159.195.210.230:…          3 │", lines)
        self.assertEqual({width_of(line) for line in lines if line.startswith(("╭", "│", "╰"))}, {37})

    def test_view_measures_the_terminal_it_draws_on(self):
        import fcntl
        import termios
        primary, secondary = os.openpty()
        fcntl.ioctl(secondary, termios.TIOCSWINSZ, struct.pack("HHHH", 30, 50, 0, 0))
        with os.fdopen(secondary, "w", encoding="utf-8") as stream, patch("shutil.get_terminal_size", return_value=os.terminal_size((200, 60))):
            view = PullView(stream, color=False)
            self.assertEqual(tuple(view._terminal_size()), (50, 30))
            # A terminal nobody sized reports 0 by 0, so the fallback size is used.
            fcntl.ioctl(secondary, termios.TIOCSWINSZ, struct.pack("HHHH", 0, 0, 0, 0))
            self.assertEqual(tuple(view._terminal_size()), (200, 60))
        os.close(primary)

    def test_terminal_stdout_gets_a_readable_error_instead_of_json(self):
        stdout, stderr = TtyStream(), TtyStream()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            self.assertEqual(main(["pull", "/nonexistent/release.json", "--progress", "human"]), 1)
            self.assertEqual(main(["pull", "/nonexistent/release.json", "--progress", "json"]), 1)
        # A redirected stderr takes the view's lines away, so stdout keeps the JSON.
        with redirect_stdout(stdout), redirect_stderr(io.StringIO()):
            self.assertEqual(main(["pull", "/nonexistent/release.json", "--progress", "human"]), 1)
        readable, data, redirected = stdout.getvalue().splitlines()
        self.assertRegex(readable, r"^error     \S")
        self.assertEqual(json.loads(data)["ok"], False)
        self.assertEqual(json.loads(redirected)["ok"], False)


if __name__ == "__main__":
    unittest.main()
