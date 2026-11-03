from __future__ import annotations

import json
import sys
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aislelock.server import Handler


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
        self.assertIn(b"AisleLock", data)

    def test_presets_include_grocery(self) -> None:
        status, data = self._request("GET", "/api/presets")
        self.assertEqual(status, 200)
        body = json.loads(data)
        ids = {item["id"] for item in body["floors"]}
        self.assertIn("grocery", ids)
        self.assertIn("vna", ids)

    def test_lock_api_returns_windows(self) -> None:
        payload = {
            "floor": {"preset": "grocery"},
            "carts": [
                {
                    "id": "CART-99",
                    "priority": 1,
                    "temp": "dry",
                    "walk": [{"aisle": "A", "picks": 2}],
                }
            ],
        }
        status, data = self._request("POST", "/api/lock", json.dumps(payload).encode())
        self.assertEqual(status, 200)
        result = json.loads(data)
        self.assertEqual(result["locked_count"], 1)
        self.assertTrue(result["all_fit"])
        self.assertEqual(result["locks"][0]["visits"][0]["aisle"], "A")

    def test_examples_list_includes_clear_wave(self) -> None:
        status, data = self._request("GET", "/api/examples")
        self.assertEqual(status, 200)
        names = json.loads(data)
        self.assertIn("clear-wave.json", names)

    def test_bad_payload_is_400(self) -> None:
        status, data = self._request("POST", "/api/lock", b"{}")
        self.assertEqual(status, 400)
        self.assertIn("error", json.loads(data))
