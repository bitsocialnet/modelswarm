"""Readable `modelswarm pull` progress for a terminal. Pipes keep the JSON events."""

import os
import shutil
import time


LABEL = 11
LOG_LINES = 4
SOURCE_ROWS = 5
MAP_COLUMNS = 32
# Wide enough for a full map row (a square and a gap per column) inside the borders.
BOX_WIDTH = 2 * MAP_COLUMNS - 1 + 6
MAP_ROWS = 8
FRESH_SECONDS = 0.6
REDRAW_SECONDS = 1 / 15
SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
# Plain SGR codes resolve to the terminal's own palette, so the view stays
# readable on light and dark themes alike.
BOLD, DIM, STRIKE = "1", "2", "2;9"
RED, GREEN, YELLOW, BRIGHT = "31", "32", "33", "1;92"


def size_text(size):
    for unit, scale in (("GB", 10**9), ("MB", 10**6), ("kB", 10**3)):
        if size >= scale:
            return f"{size / scale:.1f} {unit}"
    return f"{size} B"


def duration_text(seconds):
    if seconds < 1:
        return "<1 s"
    if seconds < 60:
        return f"{seconds:.0f} s"
    if seconds < 3600:
        return f"{seconds / 60:.0f} min"
    return f"{seconds // 3600:.0f} h {seconds % 3600 / 60:.0f} min"


def plural(count, word):
    return f"{count} {word}{'s' * (count != 1)}"


def short_key(value):
    return value if len(value) <= 20 else f"{value[:12]}…{value[-4:]}"


def cell_of(piece, cells, total):
    # Cell c covers pieces [c * total // cells, (c + 1) * total // cells).
    return ((piece + 1) * cells - 1) // total


class FileProgress:
    def __init__(self, path, size, total, piece_size):
        self.path, self.size, self.total, self.piece_size = path, size, total, piece_size
        self.verified = bytearray(total)
        self.done = 0
        self.bad = set()
        self.failed = set()
        self.fresh = {}
        self.sources = {}
        self.dropped = set()
        self.log = []
        self.ready = False
        self.rate = None
        self.sample = None

    def piece(self, index):
        return f"#{index:0{max(3, len(str(self.total - 1)))}d}"


class PullView:
    """Draw the current file in a live box on a terminal; print lasting lines above it.

    Lasting lines (the release header, bad pieces, dropped sources and file
    summaries) scroll normally. The box holds the piece map, the latest pieces,
    the sources and the status, and is redrawn in place.
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
        rows = [("release", [(f"{manifest['name']} {manifest['version']}", BOLD), (f" · {manifest['license']}", DIM)])]
        if provenance.get("signed"):
            rows.append(("publisher", [(short_key(provenance["publisher"]), ""), (" ✓ signature valid", GREEN)]))
            rows.append(("manifest", [(digest[:12], ""), (" ✓ matches the signed release", GREEN)]))
        elif pinned:
            rows.append(("manifest", [(digest[:12], ""), (" unsigned · matches --manifest-sha256", DIM)]))
        else:
            rows.append(("manifest", [(digest[:12], ""), (" ! unsigned local file", YELLOW)]))
        rows.append(("files", [(f"{len(entries)} selected · {size_text(sum(entry['size'] for entry in entries))}", "")]))
        rows.extend(("skipped", [(path, ""), (" flagged format; --allow-unsafe downloads it", DIM)]) for path in skipped)
        self.transient = None
        self._print(*([(label.ljust(LABEL), DIM), *segments] for label, segments in rows), [])

    def finish(self, result):
        self._print([], [("verified".ljust(LABEL), DIM), ("✓ ", GREEN), (plural(len(result["files"]), "file"), BOLD)],
                    [("snapshot".ljust(LABEL), DIM), (result["snapshot"], "")])

    # Engine events.

    def _on_file_started(self, path, size, total_pieces, piece_size, **_):
        self.transient = None
        self.file = FileProgress(path, size, total_pieces, piece_size)
        self._draw(force=True)

    def _on_file_ready(self, verified_pieces, have=None, **_):
        file = self.file
        if have is not None:
            # One byte per piece, already verified on disk; adopted without a per-piece loop.
            file.verified = bytearray(have)
            file.done = file.verified.count(1)
        file.ready = True
        if verified_pieces:
            self._print([("· ", DIM), (f"resuming {file.path}: {plural(verified_pieces, 'piece')} already verified on disk", DIM)])
        self._draw(force=True)

    def _on_piece_verified(self, piece, source, **_):
        file = self.file
        if not file.verified[piece]:
            file.verified[piece] = 1
            file.done += 1
            if source:
                file.sources[source] = file.sources.get(source, 0) + 1
        file.bad.discard(piece)
        file.fresh[piece] = time.monotonic()
        if piece in file.failed:
            file.failed.discard(piece)
            self._print([("✓ ", GREEN), (f"piece {file.piece(piece)} fetched again from ", ""), (source or "staged data", BOLD)])
            return
        file.log = (file.log + [(piece, source or "staged data")])[-LOG_LINES:]
        self._draw()

    def _on_hash_failed(self, piece, source=None, **_):
        file = self.file
        file.bad.add(piece)
        file.failed.add(piece)
        self._print([("✗ ", RED), (f"piece {file.piece(piece)} from ", ""), (source or "an unknown source", BOLD),
                     (" failed its hash check and was discarded", RED)])

    def _on_source_banned(self, source, **_):
        self.file.dropped.add(source)
        self.file.sources.setdefault(source, 0)
        self._print([("! ", YELLOW), ("dropped ", ""), (source, BOLD), (" for sending a bad piece", DIM)])

    def _on_checkpoint_ignored(self, reason, **_):
        self._print([("· ", DIM), (f"checkpoint ignored: {reason}", DIM)])

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
            self._print([("  ", ""), (file.path, ""), ("  ", ""), *self._status(file)])

    def _on_checkpoint_saved(self, reason, **_):
        if reason not in ("interrupted", "timeout") or self.file is None:
            return
        file, self.file = self.file, None
        why = "interrupted" if reason == "interrupted" else "timed out"
        self._print([("■ ", YELLOW), (file.path, BOLD),
                     (f" {why} at {file.done}/{file.total} pieces · checkpoint saved, rerun the same pull to resume", DIM)])

    def _on_file_complete(self, path, size, seconds, **_):
        file, self.file = self.file, None
        lines = [[("✓ ", GREEN), (path, BOLD), (f"  {size_text(size)} · {plural(file.total, 'piece')} · {seconds:.1f} s", DIM)]]
        sources = [(name, count) for name, count in file.sources.items() if count]
        if sources:
            named = ", ".join(name if len(sources) == 1 else f"{name} ({count})" for name, count in sources)
            lines.append([("  from ", DIM), (named, DIM)])
        self._print(*lines)

    def _on_file_cached(self, path, **_):
        self._print([("✓ ", GREEN), (path, BOLD), ("  already in the cache", DIM)])

    def _on_file_reused(self, path, **_):
        self._print([("✓ ", GREEN), (path, BOLD), ("  already downloaded and verified", DIM)])

    # Drawing.

    def _paint(self, text, style):
        return f"\x1b[{style}m{text}\x1b[0m" if self.color and style and text else text

    def _render(self, segments, width=None):
        return "".join(self._paint(text, style) for text, style in self._fit(segments, width))

    @staticmethod
    def _fit(segments, width, pad=False):
        """Cut segments to width with an ellipsis; pad with spaces when asked."""
        out, used = [], 0
        for text, style in segments:
            if width is not None and used + len(text) > width:
                out.append((text[:max(0, width - used - 1)] + "…", style))
                return out
            out.append((text, style))
            used += len(text)
        if pad and width is not None and used < width:
            out.append((" " * (width - used), ""))
        return out

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

    def _spinner(self, now):
        return SPINNER[int(now * 12) % len(SPINNER)]

    def _terminal_size(self):
        # Measure the terminal this view draws on: stdout may be redirected
        # while stderr is still a terminal.
        try:
            return os.get_terminal_size(self.stream.fileno())
        except (AttributeError, OSError, ValueError):
            return shutil.get_terminal_size((80, 24))

    def _region(self):
        if not self.live:
            return ""
        columns, rows = self._terminal_size()
        # One column short of the edge avoids an automatic wrap, which would
        # leave more physical lines than the eraser moves back over.
        width = max(24, columns - 1)
        now = time.monotonic()
        lines = [[(self._spinner(now) + " ", GREEN), (self.transient, DIM)]] if self.transient else []
        if self.file is not None:
            lines.extend(self._box(self.file, min(BOX_WIDTH, width), rows, now))
        if len(lines) > rows - 1:
            # The eraser cannot move above the top of the screen, so a region
            # taller than the terminal would leave stale copies behind.
            lines = lines[:max(0, rows - 2)] + lines[-1:]
        self.drawn = len(lines)
        self.last_draw = now
        return "".join(self._render(line, width) + "\n" for line in lines)

    def _box(self, file, box, rows, now):
        inner = box - 4
        file.fresh = {piece: at for piece, at in file.fresh.items() if now - at < FRESH_SECONDS}
        if not file.ready:
            phase = [("· checking", DIM)]
        elif file.bad:
            phase = [("✗ bad piece", RED)]
        else:
            phase = [(f"{self._spinner(now)} pulling", GREEN)]
        phase_width = sum(len(text) for text, _ in phase)
        # ╭─ title ───── phase ─╮
        title = self._fit([(file.path, BOLD), (f" · {size_text(file.size)}", DIM)], max(1, box - 9 - phase_width))
        fill = box - 8 - sum(len(text) for text, _ in title) - phase_width
        top = [("╭─ ", DIM), *title, (" " + "─" * fill + " ", DIM), *phase, (" ─╮", DIM)]

        sources = list(file.sources.items())
        # Many peers would make the box taller than the screen. Keep the
        # busiest sources, in the order they appeared, and fold the rest.
        room = max(1, min(SOURCE_ROWS, rows - 13))
        rest = []
        if len(sources) > room:
            keep = {name for name, _ in sorted(sources, key=lambda item: -item[1])[:room - 1]}
            rest = [item for item in sources if item[0] not in keep]
            sources = [item for item in sources if item[0] in keep]
        if rest:
            sources.append((f"+{len(rest)} more", sum(count for _, count in rest)))
        # The box must fit on screen for the eraser to reach its first line.
        map_rows = max(1, min(MAP_ROWS, rows - 12 - len(sources)))
        body = [[], *self._map(file, inner, map_rows), []]
        body.extend([("✓ ", GREEN), (f"{file.piece(piece)}  ", ""), (source, DIM)] for piece, source in file.log)
        body.extend([] for _ in range(LOG_LINES - len(file.log)))
        body.append([("┄" * inner, DIM)])
        name_width = min(28, max((len(name) for name, _ in sources), default=0))
        bar_width = inner - name_width - 11
        for name, count in sources:
            dropped = name in file.dropped
            folded = bool(rest) and name == sources[-1][0]
            row = [(name[:name_width].ljust(name_width), STRIKE if dropped else DIM if folded else ""), ("  ", "")]
            if bar_width >= 6:
                row.extend(self._bar(count / file.total, bar_width, DIM if dropped else GREEN))
            row.append(("dropped".rjust(9), RED) if dropped else (str(count).rjust(9), ""))
            body.append(row)
        body.extend(([], self._status(file)))
        return [top, *([("│ ", DIM), *self._fit(row, inner, pad=True), (" │", DIM)] for row in body),
                [("╰" + "─" * (box - 2) + "╯", DIM)]]

    @staticmethod
    def _bar(fraction, width, style):
        cells = fraction * width
        filled = "━" * int(cells) + ("╸" if cells - int(cells) >= 0.5 else "")
        return [(filled, style), ("─" * (width - len(filled)), DIM)]

    def _status(self, file):
        if not file.ready:
            return [("checking data already on disk", DIM)]
        status = [(f"{file.done}/{file.total}", BOLD), (" verified", "")]
        if file.rate is not None:
            status.append((f" · {size_text(file.rate)}/s", DIM))
            if file.rate > 0 and file.done < file.total:
                status.append((f" · {duration_text((file.total - file.done) * file.piece_size / file.rate)} left", DIM))
        return status

    def _map(self, file, inner, rows):
        # One square per piece; large files share squares, hollow while partly verified.
        columns = max(1, min(MAP_COLUMNS, (inner + 1) // 2))
        cells = min(file.total, columns * rows)
        bad = {cell_of(piece, cells, file.total) for piece in file.bad}
        fresh = {cell_of(piece, cells, file.total) for piece in file.fresh}
        lines, line = [], []
        for cell in range(cells):
            start, end = cell * file.total // cells, (cell + 1) * file.total // cells
            done = file.verified.count(1, start, end)
            if cell in bad:
                glyph = ("■" if self.color else "×", RED)
            elif cell in fresh:
                glyph = ("■", BRIGHT)
            elif done == end - start:
                glyph = ("■", GREEN)
            elif done:
                glyph = ("□", GREEN)
            else:
                glyph = ("■" if self.color else "·", DIM)
            text = (" " if cell % columns else "") + glyph[0]
            if line and line[-1][1] == glyph[1]:
                line[-1] = (line[-1][0] + text, glyph[1])
            else:
                line.append((text, glyph[1]))
            if (cell + 1) % columns == 0:
                lines.append(line)
                line = []
        if line:
            lines.append(line)
        return lines
