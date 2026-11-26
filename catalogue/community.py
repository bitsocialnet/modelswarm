"""Publish discussion posts and export a local ModelSwarm community catalogue."""

import argparse
import json
from pathlib import Path
import re
import sys
import tempfile

from modelswarm.formats import is_flagged, is_flagged_path
from modelswarm.manifest import torrent_bytes
from modelswarm.releases import bridge, manifest_from_reference, parse_uri, read_key, rpc_url


def atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(content)
            stream.close()
            temporary.chmod(0o644)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def torrent_url_prefix(torrent_dir):
    try:
        relative = torrent_dir.resolve().relative_to(Path("public").resolve())
    except ValueError as error:
        raise ValueError("Torrent directory must be inside the site's public directory") from error
    if not relative.parts or any(not re.fullmatch(r"[A-Za-z0-9_-][A-Za-z0-9_.-]*", part) for part in relative.parts):
        raise ValueError("Use a torrent subdirectory under public/ with URL-safe path components")
    return f"./{relative.as_posix()}"


def export_entry(post, manifest, torrent_dir, url_prefix):
    files = []
    for file in manifest["files"]:
        torrent = None
        flagged = is_flagged(file["format"]) or is_flagged_path(file["path"])
        if file["torrent"] and not flagged:
            filename = f"{file['torrent']['infohash_v2']}.torrent"
            atomic_write(torrent_dir / filename, torrent_bytes(file))
            torrent = f"{url_prefix}/{filename}"
        files.append({
            "path": file["path"],
            "bytes": file["size"],
            "sha256": file["sha256"],
            "torrent": torrent,
            "https": None if flagged else next((item["url"] for item in file["sources"] if item["url"].startswith("https://")), None),
            "flagged": flagged,
        })
    formats = {file["format"] for file in manifest["files"]}
    weights = sorted(formats & {"gguf", "safetensors"})
    return {
        "name": manifest["name"],
        "format": weights[0] if len(weights) == 1 else "other",
        "bytes": sum(file["bytes"] for file in files),
        "seeders": None,
        "license": manifest["license"],
        "publisher": post["publisher"],
        "releaseCid": post["releaseCid"],
        "version": manifest["version"],
        "postCid": post["postCid"],
        "files": files,
        "replies": post["replies"],
    }


def sync(args, rpc):
    feed = bridge({"op": "community-list", "rpc": rpc, "community": args.community}, args.rpc_timeout)
    if feed.get("truncated") is not False:
        raise ValueError("Community scan is incomplete. The catalogue snapshot was not replaced.")
    url_prefix = torrent_url_prefix(args.torrent_dir)
    entries = []
    for post in feed["entries"]:
        release = post["release"]
        try:
            manifest, _ = manifest_from_reference(
                release["manifest"], rpc=rpc, timeout=min(20, args.rpc_timeout), allow_local=False,
            )
            if (manifest["name"], manifest["version"]) != (release["name"], release["version"]):
                raise ValueError("manifest name/version differs from its signed announcement")
        except ValueError as error:
            print(f"Skipped {release['name']} ({post['releaseCid']}): {error}", file=sys.stderr)
            continue
        entries.append(export_entry(post, manifest, args.torrent_dir, url_prefix))
    result = {"version": 1, "community": feed["community"], "entries": entries}
    atomic_write(args.output, (json.dumps(result, ensure_ascii=False) + "\n").encode("utf-8"))
    return {"output": str(args.output), "community": args.community, "releases": len(entries)}


def run(args):
    rpc = rpc_url(args.rpc)
    if args.command == "sync":
        return sync(args, rpc)
    request = {"op": f"community-{args.command}", "rpc": rpc, "privateKey": read_key(args.key)}
    if args.command == "init":
        request["title"] = args.title
    elif args.command == "share":
        selector = parse_uri(args.release_uri)
        if not selector["cid"]:
            raise ValueError("share requires a release URI pinned to an immutable #CID")
        request.update(community=args.community, **selector)
    else:
        request.update(community=args.community, cid=args.post_cid, text=args.text)
    result = bridge(request, args.rpc_timeout)
    if args.command == "share":
        return {"postCid": result["postCid"], "releaseCid": result["releaseCid"], "publisher": result["publisher"]}
    return {key: value for key, value in result.items() if key != "ok"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="host a discussion community on your PKC node")
    init.add_argument("--title", default="ModelSwarm discussion")
    share = commands.add_parser("share", help="crosspost a signed release pinned by CID")
    share.add_argument("community")
    share.add_argument("release_uri")
    reply = commands.add_parser("reply", help="publish a plain-text reply to a release crosspost")
    reply.add_argument("community")
    reply.add_argument("post_cid")
    reply.add_argument("--text", required=True)
    export = commands.add_parser("sync", help="export signed community releases and their latest replies")
    export.add_argument("community")
    export.add_argument("--output", type=Path, default=Path("src/data/community-index.json"))
    export.add_argument("--torrent-dir", type=Path, default=Path("public/community-torrents"),
                        help="torrent subdirectory under the site's public/ (default: public/community-torrents)")
    for command in (init, share, reply):
        command.add_argument("--key", type=Path, required=True)
    for command in (init, share, reply, export):
        command.add_argument("--rpc", help="use your PKC node (defaults to MODELSWARM_RPC)")
        command.add_argument("--rpc-timeout", type=float, default=120)
    try:
        result = run(parser.parse_args())
    except (OSError, ValueError) as error:
        parser.exit(1, f"{error}\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
