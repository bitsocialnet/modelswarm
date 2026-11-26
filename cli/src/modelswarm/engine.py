"""Native v2 transfers and hashing, using the experimentally verified lifecycle."""

import base64
import hashlib
import ipaddress
import os
from pathlib import Path
import socket
import stat
import tempfile
import time
from urllib.parse import unquote, urlsplit, urlunsplit

import libtorrent as lt

from .formats import validate_file_format


MIB = 1024 * 1024


class InterruptedDownload(Exception):
    pass


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(4 * MIB), b""):
            digest.update(block)
    return digest.hexdigest()


def create_file_torrent(path, piece_size=MIB):
    storage = lt.file_storage()
    storage.add_file(path.name, path.stat().st_size)
    torrent = lt.create_torrent(storage, piece_size, flags=lt.create_torrent.v2_only)
    lt.set_piece_hashes(torrent, str(path.parent))
    generated = torrent.generate()
    # Keep manifests deterministic and keep all network sources in the manifest.
    encoded = lt.bencode({key: generated[key] for key in (b"info", b"piece layers")})
    info = lt.torrent_info(encoded)
    return encoded, info


def describe_file(path, relative, format_name, sources, piece_size=MIB):
    before = path.stat()
    result = {"path": relative, "size": before.st_size, "sha256": file_sha256(path),
              "format": format_name, "pieces_root": None, "torrent": None, "sources": sources if before.st_size else []}
    if before.st_size:
        encoded, info = create_file_torrent(path, piece_size)
        result["pieces_root"] = str(info.files().root(0))
        result["torrent"] = {"infohash_v2": str(info.info_hashes().v2),
                             "metadata": base64.b64encode(encoded).decode("ascii")}
    after = path.stat()
    if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
        raise ValueError(f"file changed while hashing: {relative}")
    return result


def check_file(entry, path, check_root=True):
    if not stat.S_ISREG(path.stat().st_mode):
        raise ValueError(f"not a regular file: {entry['path']}")
    if path.stat().st_size != entry["size"]:
        raise ValueError(f"size mismatch: {entry['path']}")
    if file_sha256(path) != entry["sha256"]:
        raise ValueError(f"SHA-256 mismatch: {entry['path']}")
    validate_file_format(path, entry["format"])
    if check_root and entry["size"]:
        expected = lt.torrent_info(base64.b64decode(entry["torrent"]["metadata"]))
        _, actual = create_file_torrent(path, expected.piece_length())
        if str(actual.files().root(0)) != entry["pieces_root"]:
            raise ValueError(f"pieces root mismatch: {entry['path']}")


def peer_address(value):
    if value.startswith("["):
        end = value.find("]:")
        if end < 0:
            raise ValueError("IPv6 peers must use [address]:port")
        host, port = value[1:end], value[end + 2:]
    else:
        try:
            host, port = value.rsplit(":", 1)
        except ValueError as error:
            raise ValueError("peers must use host:port") from error
    if not host or not port.isdigit() or not 1 <= int(port) <= 65535:
        raise ValueError("invalid peer host or port")
    try:
        return str(ipaddress.ip_address(host)), int(port)
    except ValueError:
        addresses = socket.getaddrinfo(host, int(port), type=socket.SOCK_STREAM)
        return addresses[0][4][:2]


def public_source_filter():
    """Build the IP policy shared by explicit peer validation and native transfers."""
    blocked = lt.ip_filter()
    for network in ("0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8",
                    "169.254.0.0/16", "172.16.0.0/12", "192.0.0.0/24", "192.0.2.0/24",
                    "192.88.99.0/24", "192.168.0.0/16", "198.18.0.0/15", "198.51.100.0/24",
                    "203.0.113.0/24", "224.0.0.0/4", "240.0.0.0/4", "::/0"):
        subnet = ipaddress.ip_network(network)
        blocked.add_rule(str(subnet.network_address), str(subnet.broadcast_address), 1)
    # Only global-unicast IPv6, excluding documentation/special-use space.
    blocked.add_rule("2000::", "3fff:ffff:ffff:ffff:ffff:ffff:ffff:ffff", 0)
    for network in ("2001::/23", "2001:db8::/32", "2002::/16", "3fff::/20"):
        subnet = ipaddress.ip_network(network)
        blocked.add_rule(str(subnet.network_address), str(subnet.broadcast_address), 1)
    return blocked


def session_settings(discovery, rate):
    return {
        "listen_interfaces": "0.0.0.0:0,[::]:0" if discovery else "127.0.0.1:0",
        "enable_dht": discovery, "enable_lsd": False,
        "enable_upnp": False, "enable_natpmp": False,
        "enable_incoming_utp": False, "enable_outgoing_utp": False,
        "allow_multiple_connections_per_ip": True,
        "download_rate_limit": rate,
        "urlseed_max_request_bytes": MIB, "urlseed_pipeline_size": 1,
        "alert_mask": int(lt.alert.category_t.error_notification | lt.alert.category_t.status_notification
                          | lt.alert.category_t.storage_notification),
    }


def _web_seed(info, url):
    if info.num_files() == 1:
        return url
    # A virtual tail pad switches libtorrent to directory-URL semantics.
    parts = urlsplit(url)
    if unquote(parts.path.rsplit("/", 1)[-1]) != info.files().file_path(0):
        raise ValueError("web seed URL must end with the model file name")
    return urlunsplit(parts._replace(path=parts.path.rsplit("/", 1)[0] + "/"))


def _atomic_checkpoint(path, data):
    descriptor, temporary = tempfile.mkstemp(prefix=".resume-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _endpoint_text(ip, port):
    return f"[{ip}]:{port}" if ":" in ip else f"{ip}:{port}"


class SourceNames:
    """Name the sender behind a libtorrent endpoint: a peer address or an HTTP source host."""

    def __init__(self, handle, entry):
        self.handle = handle
        self.names = {}
        self.web = {}
        self.addresses = {}
        self.mirrors = []
        for source in entry["sources"]:
            parts = urlsplit(source["url"])
            port = parts.port or (443 if parts.scheme == "https" else 80)
            label = parts.hostname if parts.port is None else _endpoint_text(parts.hostname, parts.port)
            self.mirrors.append((label, parts.hostname, port))

    def observe(self):
        # Remember connection types while peers are connected; a banned or
        # finished connection is gone from the peer list by the time it is named.
        for peer in self.handle.get_peer_info():
            self.web[(str(peer.ip[0]), int(peer.ip[1]))] = peer.connection_type != lt.peer_info.standard_bittorrent

    def _resolved(self, host, port):
        if (host, port) not in self.addresses:
            try:
                self.addresses[(host, port)] = {info[4][0] for info in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)}
            except OSError:
                self.addresses[(host, port)] = set()
        return self.addresses[(host, port)]

    def __call__(self, endpoint):
        key = (str(endpoint[0]), int(endpoint[1]))
        if key not in self.names:
            if key not in self.web:
                self.observe()
            web = self.web.get(key)
            label = None
            if web is not False:
                labels = {mirror[0] for mirror in self.mirrors}
                # A single HTTP source names every web connection, including
                # redirects to a CDN address that differs from the source host.
                if web and len(labels) == 1:
                    label = labels.pop()
                else:
                    label = next((name for name, host, port in self.mirrors
                                  if port == key[1] and key[0] in self._resolved(host, port)), None)
            if label is None:
                label = f"{'http' if web else 'peer'} {_endpoint_text(*key)}"
            self.names[key] = label
        return self.names[key]

    def main(self, blocks):
        """Name the source asked for most blocks of a piece, or None if unknown."""
        if not blocks:
            return None
        counts = {}
        for endpoint in blocks.values():
            counts[endpoint] = counts.get(endpoint, 0) + 1
        return self(max(counts, key=counts.get))


def download_file(entry, directory, *, peers, discovery, timeout, rate, checkpoint_interval, cancel, emit,
                  allow_local_sources=True, piece_events=False):
    """Write only to private staging; expose bytes to consumers after validation.

    With piece_events, also emit piece_verified for every verified piece and name
    the source of failed pieces; this adds a native alert per requested block.
    """
    payload_dir = directory / "payload"
    payload_dir.mkdir(exist_ok=True)
    destination = payload_dir / Path(entry["path"]).name
    if payload_dir.is_symlink() or destination.is_symlink():
        raise ValueError("symlink in staging directory")
    if destination.exists() and (not destination.is_file() or destination.stat().st_nlink != 1):
        raise ValueError("staged payload must be a private regular file")
    checkpoint = directory / "resume.data"
    if checkpoint.is_symlink():
        raise ValueError("symlink checkpoint is not allowed")
    if checkpoint.exists() and (not checkpoint.is_file() or checkpoint.stat().st_nlink != 1):
        raise ValueError("checkpoint must be a private regular file")
    if destination.exists():
        try:
            check_file(entry, destination)
            emit("file_reused", path=entry["path"])
            return destination
        except ValueError:
            pass  # libtorrent rechecks and repairs partial or changed files below.
    if entry["size"] == 0:
        destination.write_bytes(b"")
        check_file(entry, destination)
        return destination
    if not peers and not discovery and not entry["sources"]:
        raise ValueError(f"no source for {entry['path']}; supply --peer or enable discovery")
    info = lt.torrent_info(base64.b64decode(entry["torrent"]["metadata"]))
    params = lt.add_torrent_params()
    if checkpoint.exists():
        try:
            if checkpoint.stat().st_size > 32 * MIB:
                raise ValueError("checkpoint too large")
            params = lt.read_resume_data(checkpoint.read_bytes())
            if params.info_hashes != info.info_hashes():
                raise ValueError("checkpoint torrent mismatch")
        except (RuntimeError, ValueError) as error:
            emit("checkpoint_ignored", path=entry["path"], reason=str(error))
            params = lt.add_torrent_params()
    params.ti = info
    params.save_path = str(payload_dir)
    params.trackers, params.url_seeds, params.http_seeds, params.peers = [], [], [], []
    params.flags = (lt.torrent_flags.default_flags | lt.torrent_flags.override_trackers
                    | lt.torrent_flags.override_web_seeds | lt.torrent_flags.disable_lsd | lt.torrent_flags.disable_pex)
    params.flags &= ~(lt.torrent_flags.paused | lt.torrent_flags.auto_managed)
    # Attach network sources only after any existing file has been rechecked.
    params.flags |= lt.torrent_flags.disable_dht
    settings = session_settings(discovery, rate)
    settings["alert_mask"] |= int(lt.alert.category_t.peer_notification)
    if piece_events:
        # libtorrent 2.1.1 posts no block_finished_alert, so a block's source is
        # the last connection it was requested from. Raise the queue so these
        # alerts cannot crowd out checkpoint alerts between polls.
        settings["alert_mask"] |= int(lt.alert.category_t.piece_progress_notification
                                      | lt.alert.category_t.block_progress_notification)
        settings["alert_queue_size"] = 200000
    session = lt.session(settings)
    if not allow_local_sources:
        # Applied by the native engine to actual connection endpoints;
        # a DNS preflight alone would leave a re-resolution race.
        session.set_ip_filter(public_source_filter())
    classes = lt.ip_filter()
    classes.add_rule("0.0.0.0", "255.255.255.255", 1)
    classes.add_rule("::", "ffff:ffff:ffff:ffff:ffff:ffff:ffff:ffff", 1)
    session.set_peer_class_filter(classes)
    handle = session.add_torrent(params)
    names = SourceNames(handle, entry)
    requested = {}
    started = time.monotonic()
    stopping = None
    checkpoint_deadline = None
    checkpoint_flags = lt.save_resume_flags_t.flush_disk_cache | lt.save_resume_flags_t.save_info_dict
    hash_failures = 0
    ready = False
    needs_recheck = destination.exists()
    recheck_requested = False
    recheck_finished = False
    last_progress = started
    last_checkpoint = started

    def connect_sources():
        if discovery:
            handle.unset_flags(lt.torrent_flags.disable_dht)
        for source in entry["sources"]:
            handle.add_url_seed(_web_seed(info, source["url"]))
        for peer in peers:
            handle.connect_peer(peer)

    try:
        emit("file_started", path=entry["path"], size=entry["size"], total_pieces=info.num_pieces(),
             piece_size=info.piece_length(), pid=os.getpid())
        while True:
            now = time.monotonic()
            banned = []
            for alert in session.pop_alerts():
                if isinstance(alert, lt.block_downloading_alert):
                    requested.setdefault(alert.piece_index, {})[alert.block_index] = alert.endpoint
                elif isinstance(alert, lt.piece_finished_alert):
                    if piece_events:
                        emit("piece_verified", path=entry["path"], piece=alert.piece_index,
                             source=names.main(requested.pop(alert.piece_index, None)))
                elif isinstance(alert, lt.hash_failed_alert):
                    hash_failures += 1
                    named = {"source": names.main(requested.pop(alert.piece_index, None))} if piece_events else {}
                    emit("hash_failed", path=entry["path"], piece=alert.piece_index,
                         payload_bytes_since_resume=handle.status().total_payload_download, **named)
                elif isinstance(alert, lt.peer_ban_alert):
                    # libtorrent posts the ban before the failure that caused it.
                    banned.append(names(alert.endpoint))
                elif isinstance(alert, lt.fastresume_rejected_alert):
                    emit("checkpoint_rejected", path=entry["path"])
                elif isinstance(alert, lt.torrent_checked_alert) and recheck_requested:
                    recheck_finished = True
                elif isinstance(alert, (lt.file_error_alert, lt.torrent_error_alert, lt.save_resume_data_failed_alert)):
                    raise RuntimeError(alert.message())
                elif isinstance(alert, lt.url_seed_alert):
                    emit("http_source_error", path=entry["path"])
                elif isinstance(alert, lt.torrent_paused_alert) and stopping:
                    handle.save_resume_data(checkpoint_flags)
                elif isinstance(alert, lt.save_resume_data_alert) and checkpoint_deadline is not None:
                    _atomic_checkpoint(checkpoint, bytes(lt.write_resume_data_buf(alert.params)))
                    emit("checkpoint_saved", path=entry["path"], verified_pieces=sum(alert.params.have_pieces),
                         reason=stopping or "periodic")
                    if stopping is None:
                        checkpoint_deadline = None
                        last_checkpoint = time.monotonic()
                        continue
                    if stopping == "complete":
                        if cancel.is_set():
                            raise InterruptedDownload("interrupted before final verification; downloaded data retained")
                        check_file(entry, destination, check_root=False)
                        emit("file_complete", path=entry["path"], size=entry["size"],
                             payload_bytes_since_resume=handle.status().total_payload_download,
                             hash_failures=hash_failures, seconds=round(now - started, 3))
                        return destination
                    if stopping == "interrupted":
                        raise InterruptedDownload("interrupted; partial downloads retained for the next pull")
                    raise TimeoutError(f"timeout downloading {entry['path']}; partial download retained")
            for source in banned:
                emit("source_banned", path=entry["path"], source=source)
            status = handle.status()
            if status.errc.value():
                raise RuntimeError(status.errc.message())
            checking = status.state in (lt.torrent_status.checking_files, lt.torrent_status.checking_resume_data)
            if not checking and not ready:
                if needs_recheck and not recheck_requested:
                    # force_recheck is a no-op during checking_resume_data, so
                    # request it only after that state and wait for completion.
                    recheck_requested = True
                    handle.force_recheck()
                elif not needs_recheck or recheck_finished:
                    ready = True
                    have = {"have": [piece for piece, done in enumerate(status.pieces) if done]} if piece_events else {}
                    emit("file_ready", path=entry["path"], verified_pieces=status.num_pieces, **have)
                    connect_sources()
            # A terminal save starts after any active periodic save. Libtorrent
            # returns the same alert for both, so keep only one request in flight.
            if checkpoint_deadline is not None:
                if now >= checkpoint_deadline:
                    raise TimeoutError("checkpoint timed out; partial files remain available for recheck")
            else:
                if cancel.is_set():
                    stopping = "interrupted"
                elif now - started >= timeout:
                    stopping = "timeout"
                elif ready and status.is_seeding:
                    stopping = "complete"
                if stopping:
                    # Shut down writes before the final save and verification.
                    checkpoint_deadline = now + 15
                    handle.pause()
                elif ready and status.num_pieces > 0 and now - last_checkpoint >= checkpoint_interval:
                    # Flush progress in place so the only peer stays connected.
                    checkpoint_deadline = now + 15
                    handle.save_resume_data(checkpoint_flags)
            if now - last_progress >= 2:
                names.observe()
                emit("progress", path=entry["path"], verified_pieces=status.num_pieces,
                     total_pieces=info.num_pieces(), payload_bytes_since_resume=status.total_payload_download)
                last_progress = now
            time.sleep(0.025)
    finally:
        session.pause()
        session.remove_torrent(handle)
