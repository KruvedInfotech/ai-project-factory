from __future__ import annotations

import json
import sys
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lastfree.server import Handler


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def _request(self, method: str, path: str, body: bytes | None = None) -> tuple[int, bytes]:
        conn = HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers = {"Content-Type": "application/json"} if body else {}
        conn.request(method, path, body=body, headers=headers)
        response = conn.getresponse()
        data = response.read()
        conn.close()
        return response.status, data

    def test_home_page_renders(self) -> None:
        status, data = self._request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b"LastFree", data)

    def test_clock_api_returns_lfd(self) -> None:
        payload = {
            "container": "MSCU1234567",
            "preset": "uswc_port",
            "available_on": "2026-11-10",
            "as_of": "2026-11-12",
        }
        status, data = self._request("POST", "/api/clock", json.dumps(payload).encode())
        self.assertEqual(status, 200)
        result = json.loads(data)
        self.assertEqual(result["demurrage_lfd"], "2026-11-13")
        self.assertEqual(result["projected_usd"], 0)

    def test_example_file_is_served(self) -> None:
        status, data = self._request("GET", "/api/examples/still-inside.json")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(data)["preset"], "uswc_port")

    def test_bad_payload_is_400(self) -> None:
        status, data = self._request("POST", "/api/clock", b"{}")
        self.assertEqual(status, 400)
        self.assertIn("error", json.loads(data))
