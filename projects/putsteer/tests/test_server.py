from __future__ import annotations

import json
import sys
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from putsteer.server import Handler


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
        self.assertIn(b"PutSteer", data)

    def test_presets_and_examples(self) -> None:
        status, data = self._request("GET", "/api/presets")
        self.assertEqual(status, 200)
        names = {item["id"] for item in json.loads(data)}
        self.assertIn("reserve_dc", names)
        status, data = self._request("GET", "/api/examples")
        self.assertEqual(status, 200)
        self.assertIn("inbound-wave.json", json.loads(data))

    def test_put_api_returns_assignments(self) -> None:
        payload = {
            "policy": {"preset": "reserve_dc"},
            "inbound": [
                {
                    "id": "LPN-1",
                    "sku": "RICE",
                    "qty": 10,
                    "height_mm": 1200,
                    "weight_kg": 200,
                    "temp": "dry",
                    "velocity": "A",
                    "priority": 1,
                }
            ],
            "locations": [
                {
                    "id": "R-A-01-1",
                    "zone": "A",
                    "type": "reserve",
                    "aisle": 1,
                    "bay": 1,
                    "level": 1,
                    "temp": "dry",
                    "max_pallets": 1,
                    "max_height_mm": 1800,
                    "max_weight_kg": 1000,
                }
            ],
        }
        status, data = self._request("POST", "/api/put", json.dumps(payload).encode())
        self.assertEqual(status, 200)
        result = json.loads(data)
        self.assertTrue(result["all_clear"])
        self.assertEqual(result["puts"][0]["pallet_id"], "LPN-1")
        self.assertEqual(result["puts"][0]["location_id"], "R-A-01-1")

    def test_bad_payload_is_400(self) -> None:
        status, data = self._request("POST", "/api/put", b"{}")
        self.assertEqual(status, 400)
        self.assertIn("error", json.loads(data))
