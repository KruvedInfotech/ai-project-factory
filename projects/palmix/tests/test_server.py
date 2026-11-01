from __future__ import annotations

import json
import sys
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from palmix.server import Handler


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
        self.assertIn(b"PalMix", data)

    def test_presets_include_gma(self) -> None:
        status, data = self._request("GET", "/api/presets")
        self.assertEqual(status, 200)
        body = json.loads(data)
        ids = {item["id"] for item in body["decks"]}
        self.assertIn("gma_48", ids)

    def test_mix_api_returns_placements(self) -> None:
        payload = {
            "deck": {"preset": "eur"},
            "cases": [
                {
                    "sku": "CASE-12",
                    "store": "07",
                    "family": "grocery",
                    "length_mm": 400,
                    "width_mm": 300,
                    "height_mm": 280,
                    "weight_kg": 8.5,
                    "quantity": 2,
                }
            ],
        }
        status, data = self._request("POST", "/api/mix", json.dumps(payload).encode())
        self.assertEqual(status, 200)
        result = json.loads(data)
        self.assertEqual(result["packed_count"], 2)
        self.assertTrue(result["all_fit"])

    def test_bad_payload_is_400(self) -> None:
        status, data = self._request("POST", "/api/mix", b"{}")
        self.assertEqual(status, 400)
        self.assertIn("error", json.loads(data))
