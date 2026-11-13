"""Exercise the real CLI endpoint with an isolated Hugging Face SDK process."""

from contextlib import contextmanager
import hashlib
import http.client
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.parse import urlsplit

from test_cli import gguf, http_source
from test_upstream import public_hub_fixture


class EndpointTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.source = self.root / "source"
        self.source.mkdir()
        gguf(self.source / "weights.gguf", 128 * 1024 + 79)
        (self.source / "config.json").write_text('{"model_type":"fixture"}')
        (self.source / "README.md").write_text("Endpoint fixture.\n")
        (self.source / "empty.txt").write_bytes(b"")
        (self.source / "custom.py").write_text("raise RuntimeError('must never execute')\n")
        (self.source / "nested").mkdir()
        (self.source / "nested" / "config.json").write_text('{"nested":true}')
        self.manifest = self.root / "release.json"
        self.cache = self.root / "server-cache"
        self.sequence = 0
        # Set HF_ENDPOINT before importing the SDK and exclude ambient tokens,
        # caches, offline mode, or proxies from both client and server processes.
        self.environment = {
            key: value for key, value in os.environ.items()
            if not key.startswith("HF_") and key not in {
                "HUGGING_FACE_HUB_TOKEN", "HUGGINGFACE_HUB_CACHE",
                "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
                "http_proxy", "https_proxy", "all_proxy",
            }
        }
        self.environment.update({
            "HF_HOME": str(self.root / "hf-home"),
            "HF_HUB_DISABLE_IMPLICIT_TOKEN": "1",
            "HF_HUB_DISABLE_PROGRESS_BARS": "1",
            "HF_HUB_DISABLE_TELEMETRY": "1",
            "HF_HUB_DOWNLOAD_TIMEOUT": "60",
            "HF_HUB_ETAG_TIMEOUT": "10",
            "NO_PROXY": "127.0.0.1,localhost",
        })

    def make(self, url):
        result = subprocess.run(
            [sys.executable, "-m", "modelswarm", "make", str(self.source),
             "-o", str(self.manifest), "--name", "test/model", "--version", "release-1",
             "--license", "apache-2.0", "--http-base", url],
            capture_output=True, text=True, env=self.environment, timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.commit = json.loads(result.stdout)["manifest_sha256"][:40]

    @contextmanager
    def serve(self, *options, upstream=None):
        self.sequence += 1
        log_path = self.root / f"server-{self.sequence}.jsonl"
        args = [sys.executable, "-m", "modelswarm", "serve",
                "--cache-dir", str(self.cache), "--host", "127.0.0.1", "--port", "0",
                "--no-discovery", "--timeout", "10"]
        if self.manifest.exists():
            args.extend(["--manifest", str(self.manifest)])
        args.extend(["--no-upstream"] if upstream is None else ["--upstream", upstream])
        args.extend(map(str, options))
        with log_path.open("w") as logs:
            process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=logs,
                                       text=True, env=self.environment)
            try:
                ready, _, _ = select.select([process.stdout], [], [], 15)
                if not ready:
                    self.fail("serve did not announce readiness: " + log_path.read_text())
                line = process.stdout.readline()
                self.assertTrue(line, log_path.read_text())
                announced = json.loads(line)
                self.assertEqual(announced.get("event"), "server_ready", line + log_path.read_text())
                yield announced["endpoint"], log_path
            finally:
                if process.poll() is None:
                    process.terminate()
                try:
                    stdout, _ = process.communicate(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate(timeout=5)
                    self.fail("serve did not stop after SIGTERM: " + log_path.read_text())
                self.assertEqual(process.returncode, 0, stdout + log_path.read_text())

    def request(self, endpoint, path, *, method="GET", headers=None):
        address = urlsplit(endpoint)
        connection = http.client.HTTPConnection(address.hostname, address.port, timeout=25)
        try:
            connection.request(method, path, headers=headers or {})
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def sdk(self, endpoint, script, *, cache="sdk-cache"):
        environment = {**self.environment, "HF_ENDPOINT": endpoint,
                       "HF_HUB_CACHE": str(self.root / cache)}
        result = subprocess.run([sys.executable, "-c", script], capture_output=True,
                                text=True, env=environment, timeout=90)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_sdk_metadata_selection_and_server_cache_reuse(self):
        with http_source(self.source) as (url, requests):
            self.make(url)
            with self.serve() as (endpoint, logs):
                metadata = self.sdk(endpoint, """
import json
from huggingface_hub import HfApi
api = HfApi(token=False)
info = api.model_info('test/model', revision='release-1', files_metadata=True)
tree = list(api.list_repo_tree('test/model', revision='main', recursive=True))
folder = list(api.list_repo_tree('test/model', path_in_repo='nested', revision=info.sha))
print(json.dumps({'commit': info.sha, 'siblings': [f.rfilename for f in info.siblings],
                  'tree': [f.path for f in tree], 'folder': [f.path for f in folder]}))
""")
                self.assertEqual(metadata["commit"], self.commit)
                self.assertEqual(metadata["folder"], ["nested/config.json"])
                self.assertIn("nested", metadata["tree"])
                self.assertNotIn("custom.py", metadata["siblings"])
                self.assertNotIn("custom.py", metadata["tree"])
                self.assertEqual(requests, [], "metadata requests must not download content")
                selected = self.sdk(endpoint, """
import hashlib,json
from pathlib import Path
from huggingface_hub import snapshot_download
snapshot = Path(snapshot_download('test/model', revision='main', token=False,
                                 allow_patterns=['config.json', 'nested/*', 'empty.txt']))
print(json.dumps({p.relative_to(snapshot).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in snapshot.rglob('*') if p.is_file()}))
""")
                self.assertEqual(set(selected), {"config.json", "nested/config.json", "empty.txt"})
                for path, digest in selected.items():
                    self.assertEqual(digest, hashlib.sha256((self.source / path).read_bytes()).hexdigest())
                self.assertEqual({item["file"] for item in requests}, {"config.json", "nested/config.json"})
                downloaded = self.sdk(endpoint, """
import hashlib,json
from pathlib import Path
from huggingface_hub import hf_hub_download
p = Path(hf_hub_download('test/model', 'weights.gguf', revision='release-1', token=False))
print(json.dumps({'digest': hashlib.sha256(p.read_bytes()).hexdigest()}))
""")
                self.assertEqual(downloaded["digest"], hashlib.sha256((self.source / "weights.gguf").read_bytes()).hexdigest())
                records = [json.loads(line) for line in logs.read_text().splitlines()]
                self.assertTrue(any(record.get("event") == "request" and record.get("source") == "local"
                                    for record in records))
        # The source is stopped and a new SDK cache cannot satisfy these requests.
        with self.serve() as (endpoint, logs):
            repeated = self.sdk(endpoint, f"""
import hashlib,json
from pathlib import Path
from huggingface_hub import snapshot_download
p = Path(snapshot_download('test/model', revision={self.commit!r}, token=False,
                          allow_patterns=['config.json', 'nested/*', 'empty.txt', 'weights.gguf']))
print(json.dumps({{f.relative_to(p).as_posix(): hashlib.sha256(f.read_bytes()).hexdigest()
                   for f in p.rglob('*') if f.is_file()}}))
""", cache="fresh-sdk-cache")
            self.assertEqual(repeated, {**selected, "weights.gguf": downloaded["digest"]})
            self.assertIn('"event": "file_cached"', logs.read_text())

    def test_head_pinning_ranges_and_browser_boundary(self):
        with http_source(self.source) as (url, requests):
            self.make(url)
            with self.serve() as (endpoint, _):
                status, headers, body = self.request(endpoint, "/test/model/resolve/main/weights.gguf", method="HEAD")
                pinned = f"/test/model/resolve/{self.commit}/weights.gguf"
                self.assertEqual(status, 307)
                self.assertEqual(headers["Location"], pinned)
                self.assertEqual(headers["X-Repo-Commit"], self.commit)
                self.assertEqual(body, b"")
                status, headers, _ = self.request(endpoint, pinned, method="HEAD")
                original = (self.source / "weights.gguf").read_bytes()
                self.assertEqual(status, 200)
                self.assertEqual(int(headers["Content-Length"]), len(original))
                self.assertEqual(headers["ETag"], '"' + hashlib.sha256(original).hexdigest() + '"')
                self.assertEqual(requests, [])
                for headers in ({"Host": "attacker.example"}, {"Origin": "https://attacker.example"},
                                {"Sec-Fetch-Site": "cross-site"}):
                    self.assertEqual(self.request(endpoint, pinned, headers=headers)[0], 403)
                self.assertEqual(requests, [], "rejected browser requests must not fetch content")
                for value, expected, bounds in (("bytes=17-91", original[17:92], "17-91"),
                                                 ("bytes=-13", original[-13:], f"{len(original)-13}-{len(original)-1}")):
                    with self.subTest(range=value):
                        status, headers, body = self.request(endpoint, pinned, headers={"Range": value})
                        self.assertEqual(status, 206)
                        self.assertEqual(body, expected)
                        self.assertEqual(headers["Content-Range"], f"bytes {bounds}/{len(original)}")
                status, headers, _ = self.request(endpoint, pinned, headers={"Range": "bytes=999999999-"})
                self.assertEqual(status, 416)
                self.assertEqual(headers["Content-Range"], f"bytes */{len(original)}")

    def test_shutdown_closes_a_held_keepalive_connection(self):
        connection = None
        try:
            with self.serve() as (endpoint, _):
                address = urlsplit(endpoint)
                connection = http.client.HTTPConnection(address.hostname, address.port, timeout=5)
                connection.request("GET", "/health")
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                self.assertEqual(json.loads(response.read()), {"ok": True})
                self.assertIsNotNone(connection.sock, "test must leave a persistent connection open")
                started = time.monotonic()
            self.assertLess(time.monotonic() - started, 5, "idle keepalive must not delay SIGTERM shutdown")
        finally:
            if connection is not None:
                connection.close()

    def test_local_policy_and_misses_do_not_fall_back(self):
        with http_source(self.source) as (url, requests), public_hub_fixture() as (upstream, remote):
            self.make(url)
            with self.serve(upstream=upstream) as (endpoint, _):
                cases = [
                    ("/test/model/resolve/main/custom.py", 403, "FormatBlocked"),
                    ("/test/model/resolve/main/missing.json", 404, "EntryNotFound"),
                    ("/test/model/resolve/unregistered/config.json", 404, "RevisionNotFound"),
                ]
                for path, expected_status, code in cases:
                    with self.subTest(path=path):
                        status, headers, _ = self.request(endpoint, path)
                        self.assertEqual(status, expected_status)
                        self.assertEqual(headers["X-Error-Code"], code)
                self.assertEqual(remote.requests, [])
                self.assertEqual(requests, [])
            with self.serve() as (endpoint, _):
                status, headers, _ = self.request(endpoint, "/missing/model/resolve/main/config.json")
                self.assertEqual(status, 404)
                self.assertEqual(headers["X-Error-Code"], "RepoNotFound")
            with self.serve("--allow-unsafe") as (endpoint, _):
                allowed = self.sdk(endpoint, """
import json
from pathlib import Path
from huggingface_hub import hf_hub_download
p = Path(hf_hub_download('test/model', 'custom.py', token=False))
print(json.dumps({'content': p.read_text()}))
""")
                self.assertEqual(allowed["content"], (self.source / "custom.py").read_text())

    def test_corrupt_source_never_receives_success_or_publishes_blob(self):
        with http_source(self.source, corrupt=True) as (url, requests):
            self.make(url)
            with self.serve("--timeout", "3") as (endpoint, _):
                status, _, body = self.request(endpoint, f"/test/model/resolve/{self.commit}/weights.gguf")
                self.assertIn(status, (502, 504))
                self.assertIn("error", json.loads(body))
                self.assertTrue(requests)
                digest = hashlib.sha256((self.source / "weights.gguf").read_bytes()).hexdigest()
                self.assertFalse((self.cache / "models--test--model" / "blobs" / digest).exists())

    def test_public_upstream_sdk_fallback_strips_credentials_and_reuses_cache(self):
        files = {"config.json": b'{"remote":true}', "nested/readme.txt": b"Public fixture.\n",
                 "custom.py": b"raise RuntimeError('must not execute')\n"}
        with public_hub_fixture(files=files, lfs_paths=("nested/readme.txt",)) as (upstream, remote):
            with self.serve(upstream=upstream) as (endpoint, logs):
                status, _, body = self.request(endpoint, "/api/models/fixture/public", headers={
                    "Authorization": "Bearer do-not-forward", "Cookie": "private=do-not-forward",
                })
                self.assertEqual(status, 200, body)
                self.assertEqual(json.loads(body)["sha"], remote.commit)
                status, headers, body = self.request(
                    endpoint, f"/fixture/public/resolve/{remote.commit}/config.json",
                    headers={"Authorization": "Bearer do-not-forward"},
                )
                self.assertEqual(status, 200, body)
                self.assertEqual(body, files["config.json"])
                self.assertEqual(headers["X-Modelswarm-Source"], "upstream")
                snapshot = self.sdk(endpoint, """
import json
from pathlib import Path
from huggingface_hub import snapshot_download
p = Path(snapshot_download('fixture/public', token=False))
print(json.dumps({f.relative_to(p).as_posix(): f.read_text()
                  for f in p.rglob('*') if f.is_file()}))
""")
                self.assertEqual(snapshot, {path: body.decode() for path, body in files.items() if path != "custom.py"})
                self.assertEqual(self.request(endpoint, f"/fixture/public/resolve/{remote.commit}/custom.py")[0], 403)
                for request in remote.requests:
                    self.assertNotIn("authorization", {key.lower() for key in request["headers"]})
                    self.assertNotIn("cookie", {key.lower() for key in request["headers"]})
                self.assertIn('"source": "upstream"', logs.read_text())
                count = len(remote.requests)
                # Pinned metadata lives in the endpoint process; verified blobs
                # must satisfy a second client without contacting the origin.
                repeated = self.sdk(endpoint, f"""
import json
from pathlib import Path
from huggingface_hub import snapshot_download
p = Path(snapshot_download('fixture/public', revision={remote.commit!r}, token=False))
print(json.dumps({{f.relative_to(p).as_posix(): f.read_text()
                   for f in p.rglob('*') if f.is_file()}}))
""", cache="fresh-sdk-cache")
                self.assertEqual(repeated, snapshot)
                self.assertEqual(len(remote.requests), count)


if __name__ == "__main__":
    unittest.main()
