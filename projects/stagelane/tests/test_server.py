from __future__ import annotations

import json
import sys
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stagelane.server import Handler


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
        self.assertIn(b"StageLane", data)

    def test_presets_include_grocery(self) -> None:
        status, data = self._request("GET", "/api/presets")
        self.assertEqual(status, 200)
        body = json.loads(data)
        ids = {item["id"] for item in body["yards"]}
        self.assertIn("grocery", ids)
        self.assertIn("parcel", ids)

    def test_seat_api_returns_placements(self) -> None:
        payload = {
            "yard": {"preset": "grocery"},
            "pallets": [
                {
                    "id": "PAL-99",
                    "carrier": "UPS",
                    "priority": 1,
                    "temp": "dry",
                    "door": 1,
                    "length_mm": 1200,
                    "width_mm": 1000,
                    "height_mm": 1400,
                    "weight_kg": 400,
                }
            ],
        }
        status, data = self._request("POST", "/api/seat", json.dumps(payload).encode())
        self.assertEqual(status, 200)
        result = json.loads(data)
        self.assertEqual(result["seated_count"], 1)
        self.assertTrue(result["all_fit"])
        self.assertEqual(result["seats"][0]["lane"], "L1")

    def test_examples_list_includes_clear_yard(self) -> None:
        status, data = self._request("GET", "/api/examples")
        self.assertEqual(status, 200)
        names = json.loads(data)
        self.assertIn("clear-yard.json", names)

    def test_bad_payload_is_400(self) -> None:
        status, data = self._request("POST", "/api/seat", b"{}")
        self.assertEqual(status, 400)
        self.assertIn("error", json.loads(data))
