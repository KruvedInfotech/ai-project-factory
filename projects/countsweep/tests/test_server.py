from __future__ import annotations

import json
import sys
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from countsweep.server import Handler


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
        self.assertIn(b"CountSweep", data)

    def test_presets_and_examples(self) -> None:
        status, data = self._request("GET", "/api/presets")
        self.assertEqual(status, 200)
        names = {item["id"] for item in json.loads(data)}
        self.assertIn("grocery_dc", names)
        status, data = self._request("GET", "/api/examples")
        self.assertEqual(status, 200)
        self.assertIn("due-wave.json", json.loads(data))

    def test_plan_api_returns_walk(self) -> None:
        payload = {
            "policy": {"preset": "grocery_dc"},
            "as_of": "2026-10-15",
            "locations": [
                {
                    "id": "P-A-01-1",
                    "sku": "RICE",
                    "book_qty": 10,
                    "abc": "A",
                    "aisle": 1,
                    "bay": 1,
                    "level": 1,
                    "last_counted": "2026-10-01",
                }
            ],
        }
        status, data = self._request("POST", "/api/plan", json.dumps(payload).encode())
        self.assertEqual(status, 200)
        result = json.loads(data)
        self.assertTrue(result["all_clear"])
        self.assertEqual(result["counts"][0]["location_id"], "P-A-01-1")

    def test_bad_payload_is_400(self) -> None:
        status, data = self._request("POST", "/api/plan", b"{}")
        self.assertEqual(status, 400)
        self.assertIn("error", json.loads(data))
