import hashlib
import io
import json
import tempfile
import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import patch
from urllib.request import BaseHandler, build_opener
from urllib.response import addinfourl

from import_pirateface import MetadataRedirectHandler, catalogue_entry, get_json, index_records


NAME = "owner/model"
REVISION = "7" * 40
V1, V2, DIGEST = "a" * 40, "1220" + "b" * 64, "c" * 64
MAGNET = f"magnet:?xt=urn:btih:{V1}&xt=urn:btmh:{V2}"
INDEX_MAGNET = MAGNET + f"&ws=https://pirateface.co/api/ws/{NAME}/{REVISION}/"
LISTING = {
    "repoId": NAME, "revision": REVISION, "infohash": V1, "magnet": INDEX_MAGNET, "seeders": 3, "hf": True,
    "files": [{"path": "weights.gguf", "sha256": DIGEST}],
}
SOURCE = {
    "id": NAME, "sha": REVISION, "gated": False, "private": False, "cardData": {"license": "mit"},
    "siblings": [{"rfilename": "weights.gguf", "size": 128, "lfs": {"sha256": DIGEST}}],
}


class RedirectTransport(BaseHandler):
    handler_order = 100

    def __init__(self, destination):
        self.destination = destination
        self.requested = []

    def open(self, request):
        self.requested.append(request.full_url)
        headers = Message()
        if len(self.requested) == 1:
            headers["Location"] = self.destination
            response = addinfourl(io.BytesIO(), headers, request.full_url, 302)
            response.msg = "Found"
        else:
            response = addinfourl(io.BytesIO(b'{"ok":true}'), headers, request.full_url, 200)
            response.msg = "OK"
        return response

    http_open = open
    https_open = open


class ImportTests(unittest.TestCase):
    def test_follows_same_origin_redirect(self):
        source = "https://pirateface.co/api/torrents"
        destination = "https://pirateface.co:443/api/listing"
        transport = RedirectTransport(destination)
        with patch("import_pirateface.METADATA_OPENER", build_opener(MetadataRedirectHandler(), transport)):
            self.assertEqual(get_json(source), {"ok": True})
        self.assertEqual(transport.requested, [source, destination])

    def test_rejects_origin_changes_before_sending_a_second_request(self):
        source = "https://pirateface.co/api/torrents"
        for destination in (
            "https://other.example/api/listing",
            "http://pirateface.co/api/listing",
            "https://pirateface.co:8443/api/listing",
            "https://pirateface.co:0/api/listing",
        ):
            with self.subTest(destination=destination):
                transport = RedirectTransport(destination)
                opener = build_opener(MetadataRedirectHandler(), transport)
                with patch("import_pirateface.METADATA_OPENER", opener):
                    with self.assertRaisesRegex(ValueError, "redirected away from its source"):
                        get_json(source)
                self.assertEqual(transport.requested, [source])

    def test_keeps_swarm_identity_and_drops_network_hints(self):
        listing = {**LISTING, "magnet": INDEX_MAGNET + "&tr=http://private.invalid&x.pe=10.0.0.1:7000"}
        result = catalogue_entry(listing, SOURCE)
        self.assertEqual(result["magnet"], MAGNET)
        self.assertEqual((result["bytes"], result["format"], result["seeders"]), (128, "GGUF", 3))

    def test_tracker_assisted_link_allows_only_public_announces(self):
        listing = {**LISTING, "magnet": (
            INDEX_MAGNET + "&tr=udp://tracker.pirateface.co:6969/announce"
            + "&tr=https://tracker.pirateface.co:6969/announce?key=private"
        )}
        result = catalogue_entry(listing, SOURCE)
        self.assertEqual(result["magnet"], MAGNET)
        self.assertEqual(
            result["trackedMagnet"],
            MAGNET + "&tr=udp%3A%2F%2Ftracker.pirateface.co%3A6969%2Fannounce",
        )

    def test_identifies_openvino_from_the_torrent_file_paths(self):
        files = ["openvino_model.xml", "openvino_model.bin"]
        listing = {**LISTING, "files": [{"path": path, "sha256": DIGEST} for path in files]}
        source = {**SOURCE, "siblings": [{"rfilename": path, "size": 128} for path in files]}
        self.assertEqual(catalogue_entry(listing, source)["format"], "OpenVINO")

    def test_rejects_unproven_revisions_licenses_and_access(self):
        for change in (
            {"sha": "0" * 40},
            {"cardData": {}},
            {"cardData": {"license": "gemma"}},
            {"private": True},
            {"gated": "auto"},
            {"gated": None},
        ):
            with self.subTest(change=change):
                self.assertIsNone(catalogue_entry(LISTING, {**SOURCE, **change}))
        self.assertIsNone(catalogue_entry({**LISTING, "magnet": None}, SOURCE))
        self.assertIsNone(catalogue_entry({**LISTING, "magnet": MAGNET + "&xt=urn:btih:" + "0" * 40}, SOURCE))
        self.assertIsNone(catalogue_entry(LISTING, SOURCE, {}))
        wrong_lfs = {**SOURCE["siblings"][0], "lfs": {"sha256": "0" * 64}}
        self.assertIsNone(catalogue_entry(LISTING, {**SOURCE, "siblings": [wrong_lfs]}))

    def cache(self, directory, shards):
        cache = Path(directory)
        (cache / "shards").mkdir()
        digests = {}
        for name, contents in shards.items():
            data = contents.encode()
            (cache / "shards" / name).write_bytes(data)
            digests[name] = hashlib.sha256(data).hexdigest()
        (cache / "state.json").write_text(json.dumps(
            {"build": max(name[-14:-4] for name in shards), "shards": list(shards), "digests": digests}
        ))
        return cache

    def test_dated_removals_and_relisting(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = self.cache(directory, {
                "2026-11-09.txt": INDEX_MAGNET + "\n",
                "removed-2026-11-16.txt": V1 + "\n",
            })
            self.assertEqual(index_records(cache), ("2026-11-16", {}))
        with tempfile.TemporaryDirectory() as directory:
            cache = self.cache(directory, {
                "2026-11-09.txt": INDEX_MAGNET + "\n",
                "removed-2026-11-16.txt": V1 + "\n",
                "2026-11-23.txt": INDEX_MAGNET + "\n",
            })
            build, index = index_records(cache)
            self.assertEqual(build, "2026-11-23")
            self.assertEqual(catalogue_entry(LISTING, SOURCE, index)["magnet"], MAGNET)

    def test_refuses_corrupt_removals(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = self.cache(directory, {"removed-2026-11-16.txt": V1 + "\n"})
            (cache / "shards" / "removed-2026-11-16.txt").write_text(V1)
            with self.assertRaisesRegex(ValueError, "digest"):
                index_records(cache)
        with tempfile.TemporaryDirectory() as directory:
            cache = self.cache(directory, {"removed-2026-11-16.txt": V1 + "1\n"})
            with self.assertRaisesRegex(ValueError, "removal"):
                index_records(cache)


if __name__ == "__main__":
    unittest.main()
