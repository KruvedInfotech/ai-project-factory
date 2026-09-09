from __future__ import annotations

import json
import sys
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pickpath.server import Handler


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
        self.assertIn(b"PickPath", data)

    def test_presets_and_examples(self) -> None:
        status, data = self._request("GET", "/api/presets")
        self.assertEqual(status, 200)
        presets = json.loads(data)
        self.assertTrue(any(p["id"] == "grocery_6x20" for p in presets))
        status, data = self._request("GET", "/api/examples")
        self.assertEqual(status, 200)
        self.assertIn("grocery-wave.json", json.loads(data))

    def test_route_api_returns_path(self) -> None:
        payload = {
            "warehouse": {"preset": "mini_4x8"},
            "strategy": "s_shape",
            "picks": [
                {"sku": "A", "aisle": 1, "bay": 2, "side": "L", "qty": 1},
                {"sku": "B", "aisle": 2, "bay": 6, "side": "R", "qty": 1},
            ],
        }
        status, data = self._request("POST", "/api/route", json.dumps(payload).encode())
        self.assertEqual(status, 200)
        result = json.loads(data)
        self.assertEqual(result["routed_count"], 2)
        self.assertGreater(len(result["path"]), 2)
        self.assertTrue(result["all_routed"])

    def test_bad_payload_is_400(self) -> None:
        status, data = self._request("POST", "/api/route", b"{}")
        self.assertEqual(status, 400)
        self.assertIn("error", json.loads(data))
