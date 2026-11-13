"""Experimental single-file BitTorrent v2 engine; no publisher/signature layer yet."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from urllib.parse import unquote, urlsplit, urlunsplit

import libtorrent as lt


MIB = 1024 * 1024


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(4 * MIB), b""):
            digest.update(block)
    return digest.hexdigest()


def make_torrent(source, output, piece_size=MIB):
    source, output = Path(source), Path(output)
    started = time.monotonic()
    storage = lt.file_storage()
    storage.add_file(source.name, source.stat().st_size)
    torrent = lt.create_torrent(storage, piece_size, flags=lt.create_torrent.v2_only)
    lt.set_piece_hashes(torrent, str(source.parent))
    encoded = lt.bencode(torrent.generate())
    output.write_bytes(encoded)
    info = lt.torrent_info(encoded)
    assert info.info_hashes().has_v2() and not info.info_hashes().has_v1()
    return {
        "file": source.name,
        "size": source.stat().st_size,
        "sha256": sha256(source),
        "torrent_sha256": hashlib.sha256(encoded).hexdigest(),
        "infohash_v2": str(info.info_hashes().v2),
        "pieces_root": str(info.files().root(0)),
        "piece_size": info.piece_length(),
        "pieces": info.num_pieces(),
        "torrent_bytes": len(encoded),
        "hash_and_metadata_seconds": round(time.monotonic() - started, 4),
    }


def session_settings(rate=0, local_only=True):
    settings = {
        "listen_interfaces": "127.0.0.1:0",
        "enable_dht": False,
        "enable_lsd": False,
        "enable_upnp": False,
        "enable_natpmp": False,
        "enable_incoming_utp": False,
        "enable_outgoing_utp": False,
        "allow_multiple_connections_per_ip": True,
        "alert_mask": int(lt.alert.category_t.error_notification
                          | lt.alert.category_t.status_notification
                          | lt.alert.category_t.storage_notification),
        "download_rate_limit": rate,
        "urlseed_max_request_bytes": MIB,
        "urlseed_pipeline_size": 1,
    }
    if local_only:
        settings["outgoing_interfaces"] = "127.0.0.1"
    return settings


def configure_params(info, destination, resume=None):
    # Resume blobs are private local checkpoints, never network input.
    params = lt.read_resume_data(Path(resume).read_bytes()) if resume else lt.add_torrent_params()
    if resume and params.info_hashes != info.info_hashes():
        raise ValueError("resume checkpoint belongs to a different torrent")
    params.ti = info
    params.save_path = str(Path(destination).resolve())
    params.trackers = []
    params.url_seeds = []
    params.http_seeds = []
    params.peers = []
    params.flags &= ~(lt.torrent_flags.paused | lt.torrent_flags.auto_managed
                      | lt.torrent_flags.seed_mode | lt.torrent_flags.no_verify_files)
    params.flags |= (lt.torrent_flags.disable_dht | lt.torrent_flags.disable_lsd
                     | lt.torrent_flags.disable_pex | lt.torrent_flags.override_trackers
                     | lt.torrent_flags.override_web_seeds)
    return params


def apply_rate_limits_to_loopback(session):
    # libtorrent exempts LAN peers by default; include them in global class 0.
    classes = lt.ip_filter()
    classes.add_rule("0.0.0.0", "255.255.255.255", 1)
    classes.add_rule("::", "ffff:ffff:ffff:ffff:ffff:ffff:ffff:ffff", 1)
    session.set_peer_class_filter(classes)


def verified_bytes(info, status):
    # total_done also counts unverified blocks from incomplete pieces.
    # v2 may append virtual padding to the last piece; count actual file bytes.
    size = info.files().file_size(0)
    return sum(min(info.piece_length(), size - index * info.piece_length())
               for index, have in enumerate(status.pieces) if have)


def web_seed_url(info, url):
    # A v2 tail pad makes libtorrent treat even one real file as multi-file.
    # BEP 19 then expects a directory URL and appends the torrent's file path.
    if info.num_files() > 1:
        parts = urlsplit(url)
        if unquote(parts.path.rsplit("/", 1)[-1]) != info.files().file_path(0):
            raise ValueError("padded single-file web seed URL must end with the file name")
        return urlunsplit(parts._replace(path=parts.path.rsplit("/", 1)[0] + "/"))
    return url


def download(args):
    encoded = args.torrent.read_bytes()
    if hashlib.sha256(encoded).hexdigest() != args.torrent_sha256:
        raise ValueError("torrent metadata does not match the expected SHA-256")
    info = lt.torrent_info(encoded)
    if not info.info_hashes().has_v2() or info.info_hashes().has_v1():
        raise ValueError("prototype requires a v2-only torrent")
    files = info.files()
    regular = [i for i in range(files.num_files()) if not files.file_flags(i) & lt.file_storage.flag_pad_file]
    if (regular != [0] or files.file_path(0) != Path(files.file_path(0)).name
            or files.file_flags(0) & lt.file_storage.flag_symlink):
        raise ValueError("prototype accepts one flat file only")
    args.destination.mkdir(parents=True, exist_ok=True)
    session = lt.session(session_settings(args.rate, not args.external_http))
    apply_rate_limits_to_loopback(session)
    handle = session.add_torrent(configure_params(info, args.destination, args.resume))
    if args.sequential:
        handle.set_flags(lt.torrent_flags.sequential_download)
    started = time.monotonic()
    failures = []
    resumed_pieces = None
    checkpoint_requested = False
    fallback_added = False

    def emit(event, **fields):
        print(json.dumps({"event": event, "elapsed": round(time.monotonic() - started, 4), **fields}), flush=True)

    def connect(peer):
        host, port = peer.rsplit(":", 1)
        if host != "127.0.0.1":
            raise ValueError("prototype peer connections must use loopback")
        handle.connect_peer((host, int(port)))

    for url in args.http:
        handle.add_url_seed(web_seed_url(info, url))
    for peer in args.peer:
        connect(peer)
    emit("started", pid=os.getpid(), libtorrent=lt.__version__, resume=bool(args.resume))
    try:
        while time.monotonic() - started < args.timeout:
            for alert in session.pop_alerts():
                if isinstance(alert, lt.hash_failed_alert):
                    status = handle.status()
                    failure = {"piece": alert.piece_index, "verified_pieces": status.num_pieces,
                               "elapsed": round(time.monotonic() - started, 4),
                               "payload_bytes": status.total_payload_download}
                    failures.append(failure)
                    emit("hash_failed", **{k: v for k, v in failure.items() if k != "elapsed"})
                    if not fallback_added:
                        for peer in args.peer_after_failure:
                            connect(peer)
                        for url in args.http_after_failure:
                            handle.add_url_seed(web_seed_url(info, url))
                        fallback_added = True
                elif isinstance(alert, lt.fastresume_rejected_alert):
                    raise RuntimeError(f"resume rejected: {alert.message()}")
                elif isinstance(alert, lt.torrent_paused_alert) and checkpoint_requested:
                    # pause completion follows storage shutdown; resume-save alone
                    # can snapshot before its asynchronous disk flush completes.
                    handle.save_resume_data(lt.save_resume_flags_t.flush_disk_cache | lt.save_resume_flags_t.save_info_dict)
                elif isinstance(alert, (lt.torrent_error_alert, lt.file_error_alert, lt.save_resume_data_failed_alert)):
                    raise RuntimeError(alert.message())
                elif isinstance(alert, lt.save_resume_data_alert):
                    data = bytes(lt.write_resume_data_buf(alert.params))
                    temporary = args.checkpoint.with_suffix(".tmp")
                    with temporary.open("wb") as stream:
                        stream.write(data)
                        stream.flush()
                        os.fsync(stream.fileno())
                    temporary.replace(args.checkpoint)
                    saved = lt.read_resume_data(data)
                    emit("checkpoint", verified_pieces=sum(saved.have_pieces),
                         verified_bytes=verified_bytes(info, handle.status()), checkpoint_bytes=len(data))
                    if args.hold_after_checkpoint:
                        while True:
                            time.sleep(1)
                    return
                elif isinstance(alert, lt.url_seed_alert):
                    emit("web_seed_error", message=alert.message())
            status = handle.status()
            if status.errc.value():
                raise RuntimeError(status.errc.message())
            if status.state not in (lt.torrent_status.checking_resume_data, lt.torrent_status.checking_files):
                if resumed_pieces is None:
                    resumed_pieces = status.num_pieces
                    emit("ready", verified_pieces=resumed_pieces)
                if args.stop_after and verified_bytes(info, status) >= args.stop_after and not checkpoint_requested:
                    checkpoint_requested = True
                    handle.pause()
                if status.is_seeding and not checkpoint_requested:
                    result = {
                        "verified_bytes": verified_bytes(info, status),
                        "verified_pieces": status.num_pieces,
                        "payload_bytes": status.total_payload_download,
                        "failed_bytes": status.total_failed_bytes,
                        "redundant_bytes": status.total_redundant_bytes,
                        "resumed_pieces": resumed_pieces,
                        "hash_failures": failures,
                        "sha256": sha256(args.destination / info.files().file_path(0)),
                    }
                    emit("complete", **result)
                    return
            time.sleep(0.02)
        raise TimeoutError(f"download exceeded {args.timeout}s; {handle.status()}")
    finally:
        session.pause()
        session.remove_torrent(handle)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    make = sub.add_parser("make")
    make.add_argument("source", type=Path)
    make.add_argument("torrent", type=Path)
    worker = sub.add_parser("download")
    worker.add_argument("torrent", type=Path)
    worker.add_argument("destination", type=Path)
    worker.add_argument("--torrent-sha256", required=True)
    worker.add_argument("--peer", action="append", default=[])
    worker.add_argument("--http", action="append", default=[])
    worker.add_argument("--peer-after-failure", action="append", default=[])
    worker.add_argument("--http-after-failure", action="append", default=[])
    worker.add_argument("--external-http", action="store_true")
    worker.add_argument("--sequential", action="store_true")
    worker.add_argument("--rate", type=int, default=0)
    worker.add_argument("--timeout", type=float, default=120)
    worker.add_argument("--resume", type=Path)
    worker.add_argument("--stop-after", type=int, default=0)
    worker.add_argument("--checkpoint", type=Path)
    worker.add_argument("--hold-after-checkpoint", action="store_true")
    args = parser.parse_args()
    if args.command == "make":
        print(json.dumps(make_torrent(args.source, args.torrent), indent=2))
    else:
        if args.stop_after and not args.checkpoint:
            parser.error("--stop-after requires --checkpoint")
        download(args)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"event": "error", "message": str(error)}), flush=True)
        sys.exit(1)
