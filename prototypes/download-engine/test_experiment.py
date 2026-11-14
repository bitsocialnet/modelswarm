"""Check request reports when HTTP handlers finish late or lose their connection."""

from http.client import RemoteDisconnected
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread, current_thread
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen

import experiment


class WebSeedTests(unittest.TestCase):
    def test_request_report_waits_for_handler_after_client_reads_body(self):
        handler_waiting = Event()
        release_handler = Event()
        handler = None
        join_thread = Thread.join

        def hold_after_write(_):
            nonlocal handler
            handler = current_thread()
            handler_waiting.set()
            release_handler.wait(10)

        def join(thread, *args, **kwargs):
            if thread is handler:
                release_handler.set()
            return join_thread(thread, *args, **kwargs)

        self.addCleanup(release_handler.set)
        with TemporaryDirectory() as directory:
            source = Path(directory) / "payload.bin"
            source.write_bytes(b"payload")
            with patch.object(experiment, "time", SimpleNamespace(sleep=hold_after_write)), patch.object(Thread, "join", join):
                with experiment.web_seed(source, delay=1) as (url, requests):
                    with urlopen(Request(url, headers={"Range": "bytes=0-6"}), timeout=5) as response:
                        self.assertEqual(response.read(), b"payload")
                    self.assertTrue(handler_waiting.wait(5))
                    self.assertEqual(requests, [])
            self.assertEqual(requests, [{"range": "bytes=0-6", "start": 0, "end": 6, "sent": 7, "corrupted": False}])

    def test_request_report_includes_range_when_header_write_fails(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "payload.bin"
            source.write_bytes(b"payload")
            with patch.object(BaseHTTPRequestHandler, "end_headers", side_effect=BrokenPipeError):
                with experiment.web_seed(source) as (url, requests):
                    with self.assertRaises(RemoteDisconnected):
                        urlopen(Request(url, headers={"Range": "bytes=1-5"}), timeout=5)
            self.assertEqual(requests, [{"range": "bytes=1-5", "start": 1, "end": 5, "sent": 0, "corrupted": False}])
