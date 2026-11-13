from contextlib import contextmanager
from dataclasses import dataclass, field
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, unquote, urlsplit

from modelswarm.upstream import PublicHub, UpstreamError


@dataclass
class FixtureState:
    files: dict
    lfs_paths: set
    repo: str = "fixture/public"
    commit: str = "b" * 40
    requests: list = field(default_factory=list)
    payload_overrides: dict = field(default_factory=dict)
    redirects: dict = field(default_factory=dict)
    metadata_override: object = None
    metadata_status: int = 200
    metadata_error_code: str = "RepoNotFound"
    body_delay: float = 0
    headers_delay: float = 0

    def metadata(self):
        siblings = []
        for path, payload in self.files.items():
            record = {"rfilename": path, "size": len(payload),
                      "blobId": hashlib.sha1(b"blob " + str(len(payload)).encode() + b"\0" + payload).hexdigest()}
            if path in self.lfs_paths:
                record["lfs"] = {"sha256": hashlib.sha256(payload).hexdigest(), "size": len(payload), "pointerSize": 128}
            siblings.append(record)
        return {"id": self.repo, "sha": self.commit, "siblings": siblings, "private": False, "gated": False}


@contextmanager
def public_hub_fixture(files=None, lfs_paths=()):
    """Tiny public Hub fixture shared by helper and endpoint SDK tests."""
    state = FixtureState(files if files is not None else {"config.json": b'{"model_type":"gpt2"}', "README.md": b"public fixture\n"}, set(lfs_paths))

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_HEAD(self):
            self.serve(False)

        def do_GET(self):
            self.serve(True)

        def reply(self, status, payload=b"", headers=None, body=True):
            try:
                self.send_response(status)
                for key, value in (headers or {}).items():
                    self.send_header(key, value)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                if body:
                    if state.body_delay:
                        for offset in range(0, len(payload), 16):
                            self.wfile.write(payload[offset:offset + 16])
                            self.wfile.flush()
                            time.sleep(state.body_delay)
                    else:
                        self.wfile.write(payload)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def serve(self, body):
            state.requests.append({"method": self.command, "path": self.path, "headers": dict(self.headers)})
            parts = urlsplit(self.path)
            path = unquote(parts.path)
            metadata_prefix = f"/api/models/{state.repo}/revision/"
            if path.startswith(metadata_prefix):
                if state.metadata_status != 200:
                    self.reply(state.metadata_status, headers={"X-Error-Code": state.metadata_error_code}, body=body)
                    return
                if path[len(metadata_prefix):] not in ("main", "refs/pr/1", state.commit):
                    self.reply(404, headers={"X-Error-Code": "RevisionNotFound"}, body=body)
                    return
                if parse_qs(parts.query).get("blobs") != ["true"]:
                    self.reply(400, body=body)
                    return
                data = state.metadata_override if state.metadata_override is not None else state.metadata()
                payload = data if isinstance(data, bytes) else json.dumps(data).encode()
                self.reply(200, payload, {"Content-Type": "application/json"}, body)
                return
            prefix = f"/{state.repo}/resolve/"
            if path.startswith(prefix):
                revision, _, relative = path[len(prefix):].partition("/")
                if revision != state.commit:
                    self.reply(404, headers={"X-Error-Code": "RevisionNotFound"}, body=body)
                    return
                if relative not in state.files:
                    self.reply(404, headers={"X-Error-Code": "EntryNotFound"}, body=body)
                    return
                if relative in state.redirects:
                    self.reply(302, headers={"Location": state.redirects[relative]}, body=body)
                    return
                if state.headers_delay:
                    time.sleep(state.headers_delay)
                payload = state.payload_overrides.get(relative, state.files[relative])
                record = next(item for item in state.metadata()["siblings"] if item["rfilename"] == relative)
                digest = record.get("lfs", {}).get("sha256", record["blobId"])
                self.reply(200, payload, {"ETag": f'"{digest}"', "X-Repo-Commit": state.commit}, body)
                return
            self.reply(404, headers={"X-Error-Code": "RepoNotFound"}, body=body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


class UpstreamTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()

    def tearDown(self):
        self.temporary.cleanup()

    def test_git_and_lfs_files_are_pinned_verified_and_reused(self):
        files = {"config.json": b"{}", "weights.gguf": b"GGUF fixture bytes"}
        with public_hub_fixture(files, lfs_paths={"weights.gguf"}) as (url, state):
            hub = PublicHub(self.root, url)
            model = hub.metadata(state.repo, "main")
            self.assertEqual(model.commit, state.commit)
            self.assertEqual(model.files["config.json"].algorithm, "git-sha1")
            self.assertEqual(model.files["weights.gguf"].algorithm, "sha256")
            for relative, payload in files.items():
                path, info = hub.obtain(state.repo, model.commit, relative)
                self.assertEqual(path.read_bytes(), payload)
                requests = len(state.requests)
                self.assertEqual(hub.obtain(state.repo, model.commit, relative), (path, info))
                self.assertEqual(len(state.requests), requests)
            requests = [item["path"] for item in state.requests if "/resolve/" in item["path"]]
            self.assertTrue(all(f"/resolve/{state.commit}/" in path for path in requests))
            self.assertEqual(len(requests), 2)
            self.assertFalse(list(hub.cache.rglob(".incoming-*")))

    def test_same_size_corruption_is_never_published(self):
        with public_hub_fixture({"weights.gguf": b"expected"}, {"weights.gguf"}) as (url, state):
            state.payload_overrides["weights.gguf"] = b"modified"
            hub = PublicHub(self.root, url)
            model = hub.metadata(state.repo)
            with self.assertRaises(UpstreamError) as raised:
                hub.obtain(state.repo, model.commit, "weights.gguf")
            self.assertEqual(raised.exception.code, "UpstreamVerificationError")
            self.assertEqual(list((hub.cache / "blobs").iterdir()), [])

    def test_wrong_size_is_never_published(self):
        with public_hub_fixture({"file.txt": b"expected"}) as (url, state):
            state.payload_overrides["file.txt"] = b"short"
            hub = PublicHub(self.root, url)
            model = hub.metadata(state.repo)
            with self.assertRaisesRegex(UpstreamError, "size differs"):
                hub.obtain(state.repo, model.commit, "file.txt")
            self.assertEqual(list((hub.cache / "blobs").iterdir()), [])

    def test_cached_bytes_are_reverified_without_overwriting_corruption(self):
        with public_hub_fixture({"file.txt": b"expected"}) as (url, state):
            hub = PublicHub(self.root, url)
            path, _ = hub.obtain(state.repo, state.commit, "file.txt")
            path.write_bytes(b"modified")
            with self.assertRaisesRegex(UpstreamError, "cached upstream file failed"):
                hub.obtain(state.repo, state.commit, "file.txt")
            self.assertEqual(path.read_bytes(), b"modified")

    def test_no_ambient_authentication_or_proxy(self):
        with public_hub_fixture() as (url, state):
            with patch.dict(os.environ, {"HTTP_PROXY": "http://127.0.0.1:1", "HTTPS_PROXY": "http://127.0.0.1:1",
                                         "ALL_PROXY": "http://127.0.0.1:1", "HF_TOKEN": "do-not-forward"}):
                hub = PublicHub(self.root, url)
                hub.obtain(state.repo, state.commit, "config.json")
            for request in state.requests:
                self.assertNotIn("Authorization", request["headers"])
                self.assertNotIn("Cookie", request["headers"])
                self.assertNotIn("Proxy-Authorization", request["headers"])

    def test_missing_invalid_and_colliding_metadata_is_rejected(self):
        mutations = [
            lambda data: data["siblings"][0].pop("blobId"),
            lambda data: data["siblings"][0].update(size=-1),
            lambda data: data["siblings"][0].update(size=True),
            lambda data: data["siblings"][0].update(rfilename="../escape"),
            lambda data: data["siblings"].append(dict(data["siblings"][0], rfilename="CONFIG.JSON")),
            lambda data: data.update(sha="not-a-commit"),
        ]
        with public_hub_fixture() as (url, state):
            for mutate in mutations:
                with self.subTest(mutation=mutate):
                    state.metadata_override = state.metadata()
                    mutate(state.metadata_override)
                    with self.assertRaises(UpstreamError) as raised:
                        PublicHub(self.root, url).metadata(state.repo)
                    self.assertEqual(raised.exception.code, "UpstreamMetadataError")
            self.assertFalse(any("/resolve/" in item["path"] for item in state.requests))

    def test_pinned_commit_cannot_silently_change(self):
        with public_hub_fixture() as (url, state):
            state.metadata_override = dict(state.metadata(), sha="c" * 40)
            with self.assertRaisesRegex(UpstreamError, "different commit"):
                PublicHub(self.root, url).metadata(state.repo, state.commit)

    def test_missing_repo_revision_and_entry_preserve_error_codes(self):
        with public_hub_fixture() as (url, state):
            hub = PublicHub(self.root, url)
            for repo, revision, code in (("missing/repo", "main", "RepoNotFound"), (state.repo, "absent", "RevisionNotFound")):
                with self.assertRaises(UpstreamError) as raised:
                    hub.metadata(repo, revision)
                self.assertEqual((raised.exception.status, raised.exception.code), (404, code))
            with self.assertRaises(UpstreamError) as raised:
                hub.obtain(state.repo, state.commit, "absent.txt")
            self.assertEqual((raised.exception.status, raised.exception.code), (404, "EntryNotFound"))

    def test_gated_repository_is_not_authenticated(self):
        with public_hub_fixture() as (url, state):
            state.metadata_status, state.metadata_error_code = 403, "GatedRepo"
            with self.assertRaises(UpstreamError) as raised:
                PublicHub(self.root, url).metadata(state.repo)
            self.assertEqual((raised.exception.status, raised.exception.code), (403, "GatedRepo"))

    def test_redirect_to_another_http_origin_is_rejected(self):
        with public_hub_fixture() as (url, state):
            state.redirects["config.json"] = "http://127.0.0.1:1/private"
            with self.assertRaises(UpstreamError) as raised:
                PublicHub(self.root, url).obtain(state.repo, state.commit, "config.json")
            self.assertEqual(raised.exception.code, "UnsafeUpstream")

    def test_private_https_target_is_rejected_before_connection(self):
        hub = PublicHub(self.root, "https://127.0.0.1")
        with self.assertRaises(UpstreamError) as raised:
            hub.metadata("fixture/public")
        self.assertEqual(raised.exception.code, "UnsafeUpstream")

    def test_metadata_body_limit(self):
        with public_hub_fixture() as (url, state):
            with patch("modelswarm.upstream.MAX_METADATA_BYTES", 10):
                with self.assertRaisesRegex(UpstreamError, "size limit"):
                    PublicHub(self.root, url).metadata(state.repo)

    def test_total_deadline_interrupts_slow_body(self):
        with public_hub_fixture({"file.txt": b"x" * 1024}) as (url, state):
            hub = PublicHub(self.root, url, timeout=0.2)
            hub.metadata(state.repo)
            state.body_delay = 0.1
            started = time.monotonic()
            with self.assertRaises(UpstreamError) as raised:
                hub.obtain(state.repo, state.commit, "file.txt")
            self.assertEqual(raised.exception.status, 504)
            self.assertLess(time.monotonic() - started, 1)

    def test_cancel_interrupts_header_wait(self):
        with public_hub_fixture() as (url, state):
            cancel = threading.Event()
            hub = PublicHub(self.root, url, timeout=300, cancel=cancel)
            hub.metadata(state.repo)
            state.headers_delay = 0.5
            timer = threading.Timer(0.1, cancel.set)
            started = time.monotonic()
            timer.start()
            try:
                with self.assertRaises(UpstreamError) as raised:
                    hub.obtain(state.repo, state.commit, "config.json")
                self.assertEqual(raised.exception.code, "UpstreamCancelled")
                self.assertLess(time.monotonic() - started, 0.5)
            finally:
                timer.cancel()


if __name__ == "__main__":
    unittest.main()
