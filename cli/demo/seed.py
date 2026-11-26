"""Seed only the verified files in one ModelSwarm manifest."""

import argparse
import base64
import json
from pathlib import Path
import signal
import time

import libtorrent as lt

from modelswarm.engine import check_file, session_settings
from modelswarm.manifest import load_manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--port", type=int, default=51413)
    args = parser.parse_args()

    manifest, _ = load_manifest(args.manifest)
    for entry in manifest["files"]:
        check_file(entry, args.directory / entry["path"])

    session = lt.session({
        **session_settings(False, 0),
        "listen_interfaces": f"0.0.0.0:{args.port}",
        "upload_rate_limit": 8 * 1024 * 1024,
        "connections_limit": 32,
    })
    if session.listen_port() != args.port:
        raise RuntimeError("Seeder could not bind the requested port")

    handles = []
    for entry in manifest["files"]:
        if entry["torrent"] is None:
            continue
        params = lt.add_torrent_params()
        params.ti = lt.torrent_info(base64.b64decode(entry["torrent"]["metadata"]))
        params.save_path = str((args.directory / entry["path"]).parent)
        params.flags &= ~(lt.torrent_flags.paused | lt.torrent_flags.auto_managed)
        params.flags |= lt.torrent_flags.disable_dht | lt.torrent_flags.disable_lsd | lt.torrent_flags.disable_pex
        handles.append(session.add_torrent(params))

    def stop(_signal, _frame):
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, stop)
    previous = None
    try:
        while True:
            statuses = [handle.status() for handle in handles]
            for status in statuses:
                if status.errc.value():
                    raise RuntimeError(status.errc.message())
            state = (all(status.is_seeding for status in statuses),
                     sum(status.total_payload_upload for status in statuses))
            if state != previous:
                print(json.dumps({"seeding": state[0], "payload_uploaded": state[1]}), flush=True)
                previous = state
            time.sleep(5)
    finally:
        session.pause()


if __name__ == "__main__":
    main()
