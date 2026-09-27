from __future__ import annotations

import json
import sys
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dockbook.server import Handler


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
        self.assertIn(b"DockBook", data)

    def test_presets_and_examples(self) -> None:
        status, data = self._request("GET", "/api/presets")
        self.assertEqual(status, 200)
        ids = {item["id"] for item in json.loads(data)}
        self.assertIn("fmcg_4", ids)
        status, data = self._request("GET", "/api/examples")
        self.assertEqual(status, 200)
        self.assertIn("morning-inbound.json", json.loads(data))

    def test_book_api_returns_assignments(self) -> None:
        payload = {
            "yard": {"preset": "mini_2"},
            "trailers": [
                {
                    "id": "T1",
                    "carrier": "Local",
                    "direction": "inbound",
                    "length_m": 10,
                    "duration_min": 45,
                    "window_start": "09:00",
                    "window_end": "12:00",
                }
            ],
        }
        status, data = self._request("POST", "/api/book", json.dumps(payload).encode())
        self.assertEqual(status, 200)
        result = json.loads(data)
        self.assertEqual(result["booked_count"], 1)
        self.assertTrue(result["all_booked"])
        self.assertEqual(result["bookings"][0]["door_id"], "A")

    def test_bad_payload_is_400(self) -> None:
        status, data = self._request("POST", "/api/book", b"{}")
        self.assertEqual(status, 400)
        self.assertIn("error", json.loads(data))
