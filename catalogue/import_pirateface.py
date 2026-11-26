#!/usr/bin/env python3
"""Build a static catalogue from public Pirate Face torrents and pinned source evidence."""

import argparse
import base64
import hashlib
import json
import re
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


REPO = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}/[A-Za-z0-9][A-Za-z0-9_.-]{0,95}")
SHA1 = re.compile(r"[0-9a-f]{40}", re.IGNORECASE)
SHA256 = re.compile(r"[0-9a-f]{64}", re.IGNORECASE)
BTMH = re.compile(r"1220[0-9a-f]{64}", re.IGNORECASE)
SHARD = re.compile(r"(removed-)?(\d{4}-\d{2}-\d{2})\.txt")
LICENSES = {"apache-2.0", "mit", "wtfpl", "openmdw-1.1"}
FORMAT_NAMES = {".gguf": "GGUF", ".safetensors": "Safetensors", ".onnx": "ONNX", ".pt": "PyTorch", ".pth": "PyTorch"}
PUBLIC_TRACKERS = (
    "udp://tracker.pirateface.co:6969/announce",
    "http://tracker.pirateface.co:6969/announce",
)
MAX_JSON = 16 * 1024 * 1024


def magnet_query(magnet):
    if not isinstance(magnet, str) or not magnet.startswith("magnet:?") or len(magnet) > 8192:
        return {}
    try:
        return parse_qs(magnet.removeprefix("magnet:?"), max_num_fields=32)
    except ValueError:
        return {}


def infohashes(query):
    """Keep the original v1 and v2 identities, independent of trackers and webseeds."""
    hashes = {}
    for target in query.get("xt", ()):
        prefix, separator, digest = target.rpartition(":")
        if not separator or prefix not in ("urn:btih", "urn:btmh"):
            continue
        if prefix == "urn:btih" and re.fullmatch(r"[A-Z2-7]{32}", digest, re.IGNORECASE):
            digest = base64.b32decode(digest, casefold=True).hex()
        pattern = SHA1 if prefix == "urn:btih" else BTMH
        if not pattern.fullmatch(digest) or (prefix in hashes and hashes[prefix] != digest.lower()):
            return {}
        hashes[prefix] = digest.lower()
    return hashes


def tracked_magnet(magnet, query):
    """Keep only Pirate Face's public trackers, without webseeds or keyed trackers."""
    announced = query.get("tr", ())
    trackers = [f"&tr={quote(url, safe='')}" for url in PUBLIC_TRACKERS if url in announced]
    return magnet + "".join(trackers) if trackers else None


def index_records(cache):
    """Read a completed pf index sync, refusing incomplete state or unreadable removals."""
    state = json.loads((cache / "state.json").read_text(encoding="utf-8"))
    shards = state["shards"]
    digests = state["digests"]
    if not shards or len(shards) != len(set(shards)) or set(shards) != set(digests):
        raise ValueError("Incomplete Pirate Face index sync")
    dates = {}
    for name in shards:
        match = SHARD.fullmatch(name)
        if not match:
            raise ValueError(f"Unrecognized index shard: {name}")
        dates.setdefault(match[2], {})["removed" if match[1] else "added"] = name
    if state["build"] != max(dates):
        raise ValueError("Pirate Face index dates do not match the recorded build")

    def read(name):
        data = (cache / "shards" / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != digests[name]:
            raise ValueError(f"Index shard digest differs: {name}")
        return data.decode("utf-8").splitlines()

    records = {}
    for _, files in sorted(dates.items()):
        for magnet in read(files["added"]) if "added" in files else ():
            query = magnet_query(magnet.strip())
            hashes = infohashes(query)
            seeds = query.get("ws", [])
            if "urn:btih" not in hashes or len(seeds) != 1:
                continue
            try:
                webseed = urlsplit(seeds[0])
            except ValueError:
                continue
            parts = webseed.path.strip("/").split("/")
            if webseed.scheme != "https" or webseed.netloc != "pirateface.co" or len(parts) != 5:
                continue
            name = "/".join(parts[2:4])
            revision = parts[4]
            if parts[:2] == ["api", "ws"] and REPO.fullmatch(name) and SHA1.fullmatch(revision):
                records[name] = (revision.lower(), hashes)
        if "removed" in files:
            removals = files["removed"]
            removed = {line.strip().lower() for line in read(removals) if line.strip()}
            if any(not SHA1.fullmatch(digest) for digest in removed):
                raise ValueError(f"Invalid removal file: {removals}")
            records = {name: record for name, record in records.items() if record[1]["urn:btih"] not in removed}
    return state["build"], records


def origin(url):
    parts = urlsplit(url)
    if parts.username is not None or parts.password is not None:
        raise ValueError("Metadata URL must not contain credentials")
    port = parts.port
    if port is None:
        port = 443 if parts.scheme == "https" else 80
    return parts.scheme, parts.hostname, port


class MetadataRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if origin(req.full_url) != origin(newurl):
            raise ValueError("Metadata request redirected away from its source")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


METADATA_OPENER = build_opener(MetadataRedirectHandler())


def get_json(url):
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "ModelSwarm catalogue import"})
    try:
        with METADATA_OPENER.open(request, timeout=25) as response:
            data = response.read(MAX_JSON + 1)
    except HTTPError as error:
        if error.code in (401, 403, 404, 410):
            return {}
        raise
    if len(data) > MAX_JSON:
        raise ValueError("Metadata response is too large")
    result = json.loads(data)
    return result if isinstance(result, dict) else {}


def evidence_for(name):
    listing = get_json("https://pirateface.co/api/torrents?" + urlencode({"repo": name}))
    revision = listing.get("revision")
    if listing.get("repoId") != name or not isinstance(revision, str) or not SHA1.fullmatch(revision):
        return listing, {}
    source = get_json(f"https://huggingface.co/api/models/{name}/revision/{revision}?blobs=true")
    return listing, source


def catalogue_entry(listing, source, index=None):
    """Require a public magnet and a matching, ungated, permissively licensed origin revision."""
    name = listing.get("repoId")
    revision = listing.get("revision")
    card = source.get("cardData")
    license_id = card.get("license") if isinstance(card, dict) else None
    if not isinstance(name, str) or not REPO.fullmatch(name):
        return None
    if not isinstance(revision, str) or not SHA1.fullmatch(revision):
        return None
    if listing.get("hf") is not True or source.get("id") != name or source.get("sha") != revision:
        return None
    if source.get("private") is not False or source.get("gated") is not False:
        return None
    if not isinstance(license_id, str) or license_id not in LICENSES:
        return None

    query = magnet_query(listing.get("magnet"))
    hashes = infohashes(query)
    if "urn:btih" not in hashes or hashes["urn:btih"] != listing.get("infohash"):
        return None
    if index is not None and index.get(name) != (revision, hashes):
        return None

    listed_files = listing.get("files") or []
    source_files = {file["rfilename"]: file for file in source.get("siblings", [])}
    paths, sizes = set(), []
    for file in listed_files:
        path = file.get("path")
        digest = file.get("sha256")
        if path in paths or path not in source_files or not isinstance(digest, str) or not SHA256.fullmatch(digest):
            return None
        reference = source_files[path]
        if reference.get("lfs") and reference["lfs"].get("sha256") != digest:
            return None
        paths.add(path)
        sizes.append(reference.get("size"))
    extensions = {Path(path).suffix.lower() for path in paths}
    model_format = next((label for ext, label in FORMAT_NAMES.items() if ext in extensions), None)
    files = {Path(path).name.lower() for path in paths}
    if model_format is None and {"openvino_model.xml", "openvino_model.bin"} <= files:
        model_format = "OpenVINO"
    if model_format is None and any(name.startswith("pytorch_model") and name.endswith(".bin") for name in files):
        model_format = "PyTorch"
    seeders = listing.get("seeders")
    magnet = "magnet:?" + "&".join(f"xt={kind}:{hashes[kind]}" for kind in sorted(hashes))
    entry = {
        "name": name,
        "format": model_format or ("Other" if paths else "Unknown"),
        "bytes": sum(sizes) if sizes and all(type(size) is int and size >= 0 for size in sizes) else None,
        "seeders": seeders if type(seeders) is int and seeders >= 0 else None,
        "license": license_id,
        "magnet": magnet,
        "revision": revision,
        "upstream": f"https://huggingface.co/{name}/tree/{revision}",
    }
    if tracked := tracked_magnet(magnet, query):
        entry["trackedMagnet"] = tracked
    return entry


def read_evidence(path):
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                row = json.loads(line)
                yield row["listing"], row["source"]


def collect_entries(evidence, index):
    entries = {}
    for listing, source in evidence:
        entry = catalogue_entry(listing, source, index)
        if entry:
            entries[entry["name"]] = entry
    return entries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sources = parser.add_mutually_exclusive_group(required=True)
    sources.add_argument("--repos", type=Path, help="repository names, one per line; read public HTTPS evidence")
    sources.add_argument("--evidence", type=Path, help="offline JSONL containing public listing and source responses")
    parser.add_argument("--index-cache", type=Path, help="optional completed pf index cache directory (with state.json)")
    parser.add_argument("--observed-at", help="timestamp for offline seed counts, with a timezone")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    build, index = index_records(args.index_cache) if args.index_cache else (None, None)
    observed_at = None
    if args.observed_at:
        observed_at = datetime.fromisoformat(args.observed_at.replace("Z", "+00:00"))
        if observed_at.tzinfo is None:
            parser.error("--observed-at must include a timezone")

    if args.repos:
        observed_at = datetime.now(timezone.utc)
        names = dict.fromkeys(args.repos.read_text(encoding="utf-8").split())
        if not names or any(not REPO.fullmatch(name) for name in names):
            parser.error("--repos must contain valid owner/model names")
        eligible_names = (name for name in names if index is None or name in index)
        with ThreadPoolExecutor(max_workers=4) as pool:
            entries = collect_entries(pool.map(evidence_for, eligible_names), index)
    else:
        entries = collect_entries(read_evidence(args.evidence), index)

    output = {
        "version": 1,
        "entries": sorted(entries.values(), key=lambda entry: entry["name"].casefold()),
    }
    if observed_at:
        output["observedAt"] = observed_at.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    if build:
        output["indexBuild"] = build
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=args.output.parent, delete=False) as temporary:
        pending = Path(temporary.name)
        try:
            json.dump(output, temporary, indent=2)
            temporary.write("\n")
            temporary.close()
            pending.replace(args.output)
        finally:
            pending.unlink(missing_ok=True)
    print(f"Wrote {len(entries)} public torrents to {args.output}")


if __name__ == "__main__":
    main()
