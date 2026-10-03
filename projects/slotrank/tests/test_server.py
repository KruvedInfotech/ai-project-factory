from __future__ import annotations

import json
import sys
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from slotrank.server import Handler


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
        self.assertIn(b"SlotRank", data)

    def test_presets_and_examples(self) -> None:
        status, data = self._request("GET", "/api/presets")
        self.assertEqual(status, 200)
        names = {item["id"] for item in json.loads(data)}
        self.assertIn("grocery_6", names)
        status, data = self._request("GET", "/api/examples")
        self.assertEqual(status, 200)
        self.assertIn("mis-slotted-grocery.json", json.loads(data))

    def test_slot_api_returns_placements(self) -> None:
        payload = {
            "warehouse": {"preset": "mini_3"},
            "skus": [
                {
                    "sku": "MILK",
                    "picks": 20,
                    "cube": 8,
                    "weight_kg": 4,
                    "slot_type": "case",
                    "current": "A3-04",
                }
            ],
        }
        status, data = self._request("POST", "/api/slot", json.dumps(payload).encode())
        self.assertEqual(status, 200)
        result = json.loads(data)
        self.assertTrue(result["all_slotted"])
        self.assertEqual(result["placements"][0]["sku"], "MILK")

    def test_bad_payload_is_400(self) -> None:
        status, data = self._request("POST", "/api/slot", b"{}")
        self.assertEqual(status, 400)
        self.assertIn("error", json.loads(data))
