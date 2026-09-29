from __future__ import annotations

import json
import sys
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wavecut.server import Handler


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
        self.assertIn(b"WaveCut", data)

    def test_presets_and_examples_list(self) -> None:
        status, data = self._request("GET", "/api/presets")
        self.assertEqual(status, 200)
        presets = json.loads(data)
        self.assertTrue(any(item["id"] == "grocery_am" for item in presets))
        status, data = self._request("GET", "/api/examples")
        self.assertEqual(status, 200)
        self.assertIn("morning-stores.json", json.loads(data))

    def test_cut_api_returns_assignments(self) -> None:
        payload = {
            "shift": {"preset": "mini_3"},
            "orders": [
                {
                    "id": "A1",
                    "channel": "store",
                    "zone": "ambient",
                    "lines": 2,
                    "units": 4,
                    "cube_m3": 0.3,
                    "pick_min": 15,
                    "cutoff": "10:00",
                }
            ],
        }
        status, data = self._request("POST", "/api/cut", json.dumps(payload).encode())
        self.assertEqual(status, 200)
        result = json.loads(data)
        self.assertEqual(result["assigned_count"], 1)
        self.assertTrue(result["all_cut"])

    def test_bad_payload_is_400(self) -> None:
        status, data = self._request("POST", "/api/cut", b"{}")
        self.assertEqual(status, 400)
        self.assertIn("error", json.loads(data))
