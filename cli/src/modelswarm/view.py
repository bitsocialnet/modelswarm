"""Readable `modelswarm pull` progress for a terminal. Pipes keep the JSON events."""

import os
import shutil
import time


LABEL = 10
LOG_LINES = 4
MAP_COLUMNS = 64
MAP_ROWS = 8
METER = 12
REDRAW_SECONDS = 0.1
BOLD, DIM, RED, GREEN, YELLOW = "1", "2", "31", "32", "33"


def size_text(size):
    for unit, scale in (("GB", 10**9), ("MB", 10**6), ("kB", 10**3)):
        if size >= scale:
            return f"{size / scale:.1f} {unit}"
    return f"{size} B"


def short_key(value):
    return value if len(value) <= 20 else f"{value[:12]}…{value[-4:]}"


class FileProgress:
    def __init__(self, path, size, total, piece_size):
        self.path, self.size, self.total, self.piece_size = path, size, total, piece_size
        self.verified = bytearray(total)
        self.done = 0
        self.bad = set()
        self.failed = set()
        self.sources = {}
        self.dropped = set()
        self.log = []
        self.ready = False
        self.rate = None
        self.sample = None

    def piece(self, index):
        return f"#{index:0{max(3, len(str(self.total - 1)))}d}"


class PullView:
    """Draw a live piece map on a terminal; print only lasting lines elsewhere.

    Lasting lines (the release header, bad pieces, dropped sources and file
    summaries) scroll normally. The current file's map, recent pieces, sources
    and status are redrawn in place below them.
    """

    def __init__(self, stream, *, live=None, color=None):
        self.stream = stream
        if live is None:
            live = stream.isatty() and os.environ.get("TERM") != "dumb"
        self.live = live
        self.color = live and not os.environ.get("NO_COLOR") if color is None else color
        self.file = None
        self.transient = None
        self.drawn = 0
        self.last_draw = 0.0

    def __call__(self, event, **fields):
        handler = getattr(self, f"_on_{event}", None)
        if handler is not None:
            handler(**fields)

    # Lasting output.

    def resolving(self, uri):
        self.transient = f"resolving {uri}"
        self._draw(force=True)

    def start(self, manifest, digest, entries, skipped, provenance, pinned):
        rows = [("release", [(f"{manifest['name']} {manifest['version']}", BOLD), (f"  {manifest['license']}", DIM)])]
        if provenance.get("signed"):
            rows.append(("publisher", [(short_key(provenance["publisher"]), ""), ("  signature valid", GREEN)]))
            rows.append(("manifest", [(digest[:12], ""), ("  matches the signed release", GREEN)]))
        elif pinned:
            rows.append(("manifest", [(digest[:12], ""), ("  unsigned, matches --manifest-sha256", DIM)]))
        else:
            rows.append(("manifest", [(digest[:12], ""), ("  unsigned local file", YELLOW)]))
        rows.append(("files", [(f"{len(entries)} selected, {size_text(sum(entry['size'] for entry in entries))}", "")]))
        rows.extend(("skipped", [(path, ""), ("  flagged format; --allow-unsafe downloads it", DIM)]) for path in skipped)
        self.transient = None
        self._print(*([(label.ljust(LABEL), DIM), *segments] for label, segments in rows), [])

    def finish(self, result):
        count = len(result["files"])
        self._print([], [("verified".ljust(LABEL), DIM), (f"{count} file{'s' * (count != 1)}", "")],
                    [("snapshot".ljust(LABEL), DIM), (result["snapshot"], "")])

    # Engine events.

    def _on_file_started(self, path, size, total_pieces, piece_size, **_):
        self.transient = None
        self.file = FileProgress(path, size, total_pieces, piece_size)
        self._draw(force=True)

    def _on_file_ready(self, verified_pieces, have=(), **_):
        file = self.file
        for piece in have:
            if not file.verified[piece]:
                file.verified[piece] = 1
                file.done += 1
        file.ready = True
        if verified_pieces:
            self._print([("resume", DIM), (f"  {file.path}  {verified_pieces} piece{'s' * (verified_pieces != 1)} already verified on disk", DIM)])
        self._draw(force=True)

    def _on_piece_verified(self, piece, source, **_):
        file = self.file
        if not file.verified[piece]:
            file.verified[piece] = 1
            file.done += 1
            if source:
                file.sources[source] = file.sources.get(source, 0) + 1
        file.bad.discard(piece)
        line = [("ok    ", GREEN), (f"{file.piece(piece)}  ", ""), (source or "staged data", DIM)]
        if piece in file.failed:
            file.failed.discard(piece)
            self._print(line + [("  fetched again", GREEN)])
            return
        file.log = (file.log + [line])[-LOG_LINES:]
        self._draw()

    def _on_hash_failed(self, piece, source=None, **_):
        file = self.file
        file.bad.add(piece)
        file.failed.add(piece)
        self._print([("fail  ", RED), (f"{file.piece(piece)}  ", ""), (source or "unknown source", ""), ("  hash mismatch, piece discarded", RED)])

    def _on_source_banned(self, source, **_):
        self.file.dropped.add(source)
        self.file.sources.setdefault(source, 0)
        self._print([("drop  ", YELLOW), (source, ""), ("  sent a bad piece; no more requests", DIM)])

    def _on_checkpoint_ignored(self, reason, **_):
        self._print([("resume", DIM), (f"  checkpoint ignored: {reason}", DIM)])

    def _on_progress(self, payload_bytes_since_resume, **_):
        file = self.file
        now = time.monotonic()
        if file.sample is not None:
            seconds = now - file.sample[0]
            if seconds > 0:
                file.rate = max(0, payload_bytes_since_resume - file.sample[1]) / seconds
        file.sample = (now, payload_bytes_since_resume)
        if self.live:
            self._draw(force=True)
        else:
            self._print([(file.path, ""), ("  ", ""), *self._status(file)])

    def _on_checkpoint_saved(self, reason, **_):
        if reason not in ("interrupted", "timeout") or self.file is None:
            return
        file, self.file = self.file, None
        why = "interrupted" if reason == "interrupted" else "timed out"
        self._print([("stop  ", YELLOW), (file.path, BOLD),
                     (f"  {why} at {file.done}/{file.total} pieces; checkpoint saved, rerun the same pull to resume", DIM)])

    def _on_file_complete(self, path, size, seconds, **_):
        file, self.file = self.file, None
        sources = [(name, count) for name, count in file.sources.items() if count]
        named = "  " + ", ".join(name if len(sources) == 1 else f"{name} {count}" for name, count in sources) if sources else ""
        pieces = f"{file.total} piece{'s' * (file.total != 1)}"
        self._print([("ok    ", GREEN), (path, BOLD), (f"  {size_text(size)}  {pieces} in {seconds:.1f} s", DIM), (named, DIM)])

    def _on_file_cached(self, path, **_):
        self._print([("ok    ", GREEN), (path, BOLD), ("  already in the cache", DIM)])

    def _on_file_reused(self, path, **_):
        self._print([("ok    ", GREEN), (path, BOLD), ("  already downloaded and verified", DIM)])

    # Drawing.

    def _paint(self, text, style):
        return f"\x1b[{style}m{text}\x1b[0m" if self.color and style and text else text

    def _render(self, segments, width=None):
        out, used = [], 0
        for text, style in segments:
            if width is not None and used + len(text) > width:
                out.append(self._paint(text[:max(0, width - used - 1)] + "…", style))
                break
            out.append(self._paint(text, style))
            used += len(text)
        return "".join(out)

    def _print(self, *lines):
        text = "".join(self._render(line) + "\n" for line in lines)
        self.stream.write(self._erase() + text + self._region())
        self.stream.flush()

    def _draw(self, force=False):
        if not self.live or (not force and time.monotonic() - self.last_draw < REDRAW_SECONDS):
            return
        self.stream.write(self._erase() + self._region())
        self.stream.flush()

    def _erase(self):
        if not self.drawn:
            return ""
        # Move to the first line of the live region and clear to the end of the screen.
        text, self.drawn = f"\x1b[{self.drawn}F\x1b[J", 0
        return text

    def _region(self):
        if not self.live:
            return ""
        columns, rows = shutil.get_terminal_size((80, 24))
        # One column short of the edge avoids an automatic wrap, which would
        # leave more physical lines than the eraser moves back over.
        width = max(20, columns - 1)
        lines = [[(self.transient, DIM)]] if self.transient else []
        file = self.file
        if file is not None:
            lines.append([(file.path, BOLD), (f"  {size_text(file.size)}  {file.total} pieces", DIM)])
            lines.extend(self._map(file, width, max(1, min(MAP_ROWS, rows - 12))))
            lines.extend(file.log)
            name_width = min(32, max((len(name) for name in file.sources), default=0))
            for name, count in file.sources.items():
                filled = min(METER, round(METER * count / file.total))
                tally = ("  dropped", RED) if name in file.dropped else (f"  {count}", "")
                lines.append([(name[:name_width].ljust(name_width) + "  ", ""), ("█" * filled, GREEN), ("░" * (METER - filled), DIM), tally])
            lines.append(self._status(file))
        self.drawn = len(lines)
        self.last_draw = time.monotonic()
        return "".join(self._render(line, width) + "\n" for line in lines)

    def _status(self, file):
        if not file.ready:
            return [("checking staged data", DIM)]
        status = [(f"{file.done}/{file.total} verified", "")]
        if file.rate is not None:
            status.append((f"  {size_text(file.rate)}/s", DIM))
        return status

    def _map(self, file, width, rows):
        # Large files share cells: a full cell is all verified, a hollow one partly.
        cells = min(file.total, min(MAP_COLUMNS, width) * rows)
        columns = min(MAP_COLUMNS, width)
        lines, line = [], []
        for cell in range(cells):
            start, end = cell * file.total // cells, (cell + 1) * file.total // cells
            done = file.verified.count(1, start, end)
            if any(start <= piece < end for piece in file.bad):
                glyph = ("×", RED)
            elif done == end - start:
                glyph = ("▪", GREEN)
            elif done:
                glyph = ("▫", GREEN)
            else:
                glyph = ("·", DIM)
            if line and line[-1][1] == glyph[1]:
                line[-1] = (line[-1][0] + glyph[0], glyph[1])
            else:
                line.append(glyph)
            if (cell + 1) % columns == 0:
                lines.append(line)
                line = []
        if line:
            lines.append(line)
        return lines
