from __future__ import annotations

import json
import sys
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from modepick.server import Handler


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
        self.assertIn(b"ModePick", data)

    def test_cards_api_lists_trucks(self) -> None:
        status, data = self._request("GET", "/api/cards")
        self.assertEqual(status, 200)
        payload = json.loads(data)
        self.assertGreaterEqual(len(payload["trucks"]), 3)
        self.assertTrue(payload["parcel_zones"])

    def test_quote_api_returns_winner(self) -> None:
        payload = {
            "distance_km": 32,
            "origin": "DC",
            "destination": "Shop",
            "pieces": [
                {
                    "sku": "KIT",
                    "length_cm": 32,
                    "width_cm": 22,
                    "height_cm": 12,
                    "weight_kg": 0.8,
                    "quantity": 2,
                }
            ],
        }
        status, data = self._request("POST", "/api/quote", json.dumps(payload).encode())
        self.assertEqual(status, 200)
        result = json.loads(data)
        self.assertEqual(result["winner"], "parcel")
        self.assertTrue(any(q["mode"] == "ltl" for q in result["quotes"]))

    def test_bad_payload_is_400(self) -> None:
        status, data = self._request("POST", "/api/quote", b"{}")
        self.assertEqual(status, 400)
        self.assertIn("error", json.loads(data))
