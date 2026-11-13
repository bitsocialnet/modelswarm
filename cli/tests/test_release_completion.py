"""Require a native disk-flush barrier before validating downloaded release bytes."""

from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import libtorrent as lt

from modelswarm import engine
from test_cli import gguf, http_source


class ReleaseCompletionTests(unittest.TestCase):
    def test_final_verification_waits_for_paused_torrent_and_flushed_resume_alert(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            source = root / "source"
            source.mkdir()
            (source / "config.json").write_bytes(b'{"model_type":"completion-fixture"}')
            gguf(source / "tiny.gguf", 33 * 1024 + 257)
            with http_source(source) as (base, requests):
                for name, format_name in (("config.json", "json"), ("tiny.gguf", "gguf")):
                    with self.subTest(file=name):
                        entry = engine.describe_file(
                            source / name, name, format_name,
                            [{"type": "http", "url": base + name}], piece_size=16 * 1024)
                        directory = root / f"staging-{name}"
                        directory.mkdir()
                        timeline = []
                        native_session = lt.session
                        native_check = engine.check_file

                        class TracedHandle:
                            def __init__(self, handle):
                                self.native = handle

                            def __getattr__(self, attribute):
                                return getattr(self.native, attribute)

                            def pause(self, *args, **kwargs):
                                timeline.append(("pause_requested", None))
                                return self.native.pause(*args, **kwargs)

                            def save_resume_data(self, flags):
                                timeline.append(("flush_requested", int(flags)))
                                return self.native.save_resume_data(flags)

                        class TracedSession:
                            def __init__(self, *args, **kwargs):
                                self.native = native_session(*args, **kwargs)

                            def __getattr__(self, attribute):
                                return getattr(self.native, attribute)

                            def add_torrent(self, *args, **kwargs):
                                return TracedHandle(self.native.add_torrent(*args, **kwargs))

                            def remove_torrent(self, handle, *args, **kwargs):
                                return self.native.remove_torrent(handle.native, *args, **kwargs)

                            def pop_alerts(self):
                                # Record when the engine consumes each real alert,
                                # rather than recording an entire batch in advance.
                                for alert in self.native.pop_alerts():
                                    if isinstance(alert, lt.torrent_paused_alert):
                                        timeline.append(("paused_alert", None))
                                    elif isinstance(alert, lt.save_resume_data_alert):
                                        timeline.append(("flushed_alert", None))
                                    yield alert

                        def emit(event, **fields):
                            timeline.append((event, fields))

                        def verify_after_flush(value, path, **kwargs):
                            timeline.append(("final_verification", None))
                            names = [event for event, _ in timeline]
                            for required in ("pause_requested", "paused_alert", "flush_requested", "flushed_alert"):
                                self.assertIn(required, names,
                                              f"final verification ran before the native flush barrier: {timeline}")
                            order = [names.index(event) for event in (
                                "pause_requested", "paused_alert", "flush_requested", "flushed_alert", "final_verification")]
                            self.assertEqual(order, sorted(order), timeline)
                            flags = next(value for event, value in timeline if event == "flush_requested")
                            self.assertTrue(flags & int(lt.save_resume_flags_t.flush_disk_cache), timeline)
                            return native_check(value, path, **kwargs)

                        # Only observe native calls and alerts. The real torrent,
                        # HTTP transfer, disk writes, hashes, and format checks run.
                        with patch.object(engine.lt, "session", TracedSession), patch.object(
                                engine, "check_file", side_effect=verify_after_flush) as verifier:
                            destination = engine.download_file(
                                entry, directory, peers=[], discovery=False, timeout=10,
                                rate=0, checkpoint_interval=60, cancel=threading.Event(),
                                emit=emit, allow_local_sources=True)
                        verifier.assert_called_once()
                        self.assertEqual(destination.read_bytes(), (source / name).read_bytes())
                        native_check(entry, destination)
                        checkpoints = [fields for event, fields in timeline if event == "checkpoint_saved"]
                        self.assertTrue(any(fields["reason"] == "complete" for fields in checkpoints), timeline)
                        names = [event for event, _ in timeline]
                        self.assertLess(names.index("final_verification"), names.index("file_complete"), timeline)
                        self.assertTrue((directory / "resume.data").is_file())
            self.assertEqual({request["file"] for request in requests}, {"config.json", "tiny.gguf"})
            self.assertGreater(sum(request["sent"] for request in requests), 0)


if __name__ == "__main__":
    unittest.main()
