"""Bounded, isolated integration experiments. All peers and fixture HTTP stay on loopback."""

import argparse
from contextlib import contextmanager
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import threading
import time
from urllib.parse import unquote, urlparse

import libtorrent as lt

from engine import MIB, configure_params, make_torrent, session_settings, sha256


HERE = Path(__file__).resolve().parent


def require(condition, message):
    if not condition:
        raise AssertionError(message)


@contextmanager
def web_seed(source, corrupt=False, delay=0.0):
    events = []

    class WebSeedServer(ThreadingHTTPServer):
        # server_close() joins request threads so the event log is complete.
        daemon_threads = False

    class Handler(BaseHTTPRequestHandler):
        timeout = 5

        def log_message(self, *_):
            pass

        def do_HEAD(self):
            self.serve(False)

        def do_GET(self):
            self.serve(True)

        def serve(self, body):
            if unquote(urlparse(self.path).path) != "/" + source.name:
                self.send_error(404)
                return
            size = source.stat().st_size
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
            sent = 0
            changed = False
            try:
                self.send_response(206 if value else 200)
                self.send_header("Content-Length", str(end - start + 1))
                self.send_header("Accept-Ranges", "bytes")
                if value:
                    self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                self.end_headers()
                if body:
                    with source.open("rb") as stream:
                        stream.seek(start)
                        while sent < end - start + 1:
                            block = stream.read(min(64 * 1024, end - start + 1 - sent))
                            if corrupt and start + sent == 0:
                                block = bytes([block[0] ^ 0xFF]) + block[1:]
                                changed = True
                            self.wfile.write(block)
                            sent += len(block)
                            if delay:
                                time.sleep(delay)
            except (BrokenPipeError, ConnectionResetError, TimeoutError):
                pass
            finally:
                events.append({"range": value, "start": start, "end": end, "sent": sent, "corrupted": changed})

    server = WebSeedServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/{source.name}", events
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@contextmanager
def peer_seed(torrent, source, corrupt=False):
    settings = session_settings()
    if corrupt:
        # Deliberately malicious fixture ONLY. Download workers never disable checks.
        settings["disable_hash_checks"] = True
    session = lt.session(settings)
    info = lt.torrent_info(str(torrent))
    params = configure_params(info, source.parent)
    if corrupt:
        params.flags |= lt.torrent_flags.seed_mode | lt.torrent_flags.no_verify_files
    handle = session.add_torrent(params)
    deadline = time.monotonic() + 30
    while not handle.status().is_seeding:
        if time.monotonic() > deadline:
            raise TimeoutError("fixture peer did not become a seed")
        time.sleep(0.02)
    try:
        yield f"127.0.0.1:{session.listen_port()}", handle
    finally:
        session.pause()
        session.remove_torrent(handle)


def worker(torrent, manifest, destination, log, extra, checkpoint=None):
    command = [sys.executable, str(HERE / "engine.py"), "download", str(torrent), str(destination),
               "--torrent-sha256", manifest["torrent_sha256"], *extra]
    with log.open("w") as output:
        process = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 150
        killed = False
        try:
            while process.poll() is None:
                if checkpoint and any(e.get("event") == "checkpoint" for e in read_events(log)):
                    process.kill()
                    process.wait(timeout=10)
                    killed = True
                    break
                if time.monotonic() > deadline:
                    raise TimeoutError(f"worker timed out: {log}")
                time.sleep(0.05)
            require(killed or process.returncode == 0, f"worker failed: {log.read_text()}")
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)
    events = read_events(log)
    event = "checkpoint" if checkpoint else "complete"
    matches = [e for e in events if e.get("event") == event]
    require(bool(matches), f"missing {event}: {events}")
    result = matches[-1]
    if not checkpoint:
        require(result["sha256"] == manifest["sha256"], "downloaded file SHA-256 mismatch")
        require(result["verified_bytes"] == manifest["size"], "file not fully verified")
    result["worker_pid"] = next(e["pid"] for e in events if e.get("event") == "started")
    result["killed_after_checkpoint"] = killed
    return result


def read_events(path):
    events = []
    for line in path.read_text().splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            pass  # The worker may still be writing its last line.
    return events


def run(args):
    root = args.output.resolve()
    # Never reuse or delete an existing run; stale checkpoints can invalidate evidence.
    root.mkdir(parents=True, exist_ok=False)
    source_dir = root / "source"
    source_dir.mkdir()
    source = source_dir / "payload.bin"
    if args.source:
        source = args.source.resolve()
    else:
        with source.open("wb") as stream:
            for index in range(args.size_mib):
                stream.write(hashlib.shake_256(f"modelswarm-fixture-{index}".encode()).digest(MIB))
    torrent = root / "payload.torrent"
    manifest = make_torrent(source, torrent)
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    report = {"libtorrent": lt.__version__, "python": platform.python_version(),
              "platform": platform.platform(), "manifest": manifest, "scenarios": {}}

    def record(name, result):
        report["scenarios"][name] = result
        (root / "results.json").write_text(json.dumps(report, indent=2) + "\n")
        print(f"PASS {name}: {json.dumps(result)}", flush=True)

    def fetch(name, options, destination=None, checkpoint=None):
        return worker(torrent, manifest, destination or root / name, root / f"{name}.jsonl", options, checkpoint)

    with peer_seed(torrent, source) as (peer, seed):
        result = fetch("peer_only", ["--peer", peer])
        result["seed_payload_uploaded"] = seed.status().total_payload_upload
        require(result["seed_payload_uploaded"] >= manifest["size"], "peer did not supply the file")
        record("peer_only", result)

    with web_seed(source) as (url, requests):
        result = fetch("http_only", ["--http", url])
    result["http_bytes_sent"] = sum(r["sent"] for r in requests)
    require(result["http_bytes_sent"] >= manifest["size"], "HTTP did not supply the file")
    require(any(r["range"] for r in requests), "HTTP range requests were not exercised")
    (root / "http_only.requests.json").write_text(json.dumps(requests, indent=2))
    record("http_only", result)

    if args.transport_only:
        print(f"Evidence: {root / 'results.json'}", flush=True)
        return

    with peer_seed(torrent, source) as (peer, seed), web_seed(source, delay=0.001) as (url, requests):
        result = fetch("mixed", ["--peer", peer, "--http", url, "--rate", str(32 * MIB)])
        result["seed_payload_uploaded"] = seed.status().total_payload_upload
    result["http_bytes_sent"] = sum(r["sent"] for r in requests)
    require(result["seed_payload_uploaded"] > 0 and result["http_bytes_sent"] > 0, "both sources must transfer data")
    record("mixed", result)

    with peer_seed(torrent, source) as (peer, _), web_seed(source, corrupt=True) as (url, requests):
        result = fetch("corrupt_http", ["--http", url, "--peer-after-failure", peer, "--rate", str(args.fault_rate_mib * MIB), "--sequential"])
    require(result["hash_failures"], "corrupted HTTP piece was not rejected")
    require(result["hash_failures"][0]["payload_bytes"] < manifest["size"], "corruption detected only after full download")
    require(any(r["corrupted"] for r in requests), "HTTP corruption was not injected")
    result["http_corrupted_responses"] = sum(r["corrupted"] for r in requests)
    record("corrupt_http", result)

    bad_dir = root / "malicious-peer"
    bad_dir.mkdir()
    bad_file = bad_dir / source.name
    shutil.copyfile(source, bad_file)
    with bad_file.open("r+b") as stream:
        first = stream.read(1)
        stream.seek(0)
        stream.write(bytes([first[0] ^ 0xFF]))
    with peer_seed(torrent, bad_file, corrupt=True) as (peer, _), web_seed(source) as (url, requests):
        result = fetch("corrupt_peer", ["--peer", peer, "--http-after-failure", url, "--rate", str(args.fault_rate_mib * MIB), "--sequential"])
    require(result["hash_failures"], "malicious peer did not trigger receiver-side hash failure")
    require(result["hash_failures"][0]["payload_bytes"] < manifest["size"], "peer corruption detected too late")
    require(sum(r["sent"] for r in requests) > 0, "healthy fallback never transferred data")
    record("corrupt_peer", result)

    # Loopback peers bypass session rate limits; throttle the fixture itself.
    with web_seed(source, delay=0.003) as (url, _):
        destination = root / "resume"
        checkpoint = root / "resume.data"
        partial = fetch("resume_checkpoint", ["--http", url, "--rate", str(8 * MIB),
                        "--stop-after", str(manifest["size"] // 4), "--checkpoint", str(checkpoint),
                        "--hold-after-checkpoint"], destination, checkpoint)
        require(0 < partial["verified_pieces"] < manifest["pieces"], "checkpoint must be partial")
        saved = lt.read_resume_data(checkpoint.read_bytes())
        have = list(saved.have_pieces)
    # A separate server records only the fresh process's requests.
    with web_seed(source) as (url, requests):
        result = fetch("resume_restart", ["--http", url, "--resume", str(checkpoint)], destination)
    require(result["worker_pid"] != partial["worker_pid"], "resume must use a new process")
    require(result["resumed_pieces"] >= partial["verified_pieces"], "verified progress was lost")
    require(result["payload_bytes"] < manifest["size"], "resume downloaded the entire file again")
    for request in requests:
        for piece in range(request["start"] // manifest["piece_size"], request["end"] // manifest["piece_size"] + 1):
            require(not have[piece], f"resume re-requested verified piece {piece}")
    result["checkpoint"] = partial
    result["http_resumed_bytes"] = sum(r["sent"] for r in requests)
    (root / "resume.requests.json").write_text(json.dumps(requests, indent=2))
    record("resume_restart", result)

    if args.http_url:
        result = fetch("external_http", ["--http", args.http_url, "--external-http"])
        record("external_http", result)
    print(f"Evidence: {root / 'results.json'}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--size-mib", type=int, default=128)
    parser.add_argument("--fault-rate-mib", type=int, default=32, help="Rate cap for fault tests; raise for multi-GiB fixtures")
    parser.add_argument("--source", type=Path)
    parser.add_argument("--transport-only", action="store_true", help="Only peer-only and HTTP-only transfers, for large-file checks")
    parser.add_argument("--http-url", help="Optional real web seed matching --source, pinned to an upstream revision")
    args = parser.parse_args()
    if args.size_mib < 16:
        parser.error("--size-mib must be at least 16 for partial-transfer tests")
    run(args)
