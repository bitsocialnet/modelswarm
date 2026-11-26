import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from import_pirateface import catalogue_entry, index_records


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


class ImportTests(unittest.TestCase):
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
