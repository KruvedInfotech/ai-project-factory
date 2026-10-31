from __future__ import annotations

import json
import sys
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cartclip.server import Handler


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
        self.assertIn(b"CartClip", data)

    def test_clip_api_returns_carts(self) -> None:
        payload = {
            "warehouse": {"preset": "small_dc"},
            "cart": {"preset": "ecom_8tote"},
            "orders": [
                {
                    "id": "ORD-101",
                    "priority": 1,
                    "temp": "dry",
                    "lines": [
                        {
                            "sku": "TEE",
                            "aisle": "A",
                            "bay": 2,
                            "quantity": 2,
                            "length_mm": 200,
                            "width_mm": 150,
                            "height_mm": 40,
                            "weight_kg": 0.3,
                        }
                    ],
                }
            ],
        }
        status, data = self._request("POST", "/api/clip", json.dumps(payload).encode())
        self.assertEqual(status, 200)
        result = json.loads(data)
        self.assertEqual(result["clipped_count"], 1)
        self.assertTrue(result["all_fit"])
        self.assertEqual(result["carts"][0]["id"], "C1")

    def test_bad_payload_is_400(self) -> None:
        status, data = self._request("POST", "/api/clip", b"{}")
        self.assertEqual(status, 400)
        self.assertIn("error", json.loads(data))

    def test_examples_list_is_json(self) -> None:
        status, data = self._request("GET", "/api/examples")
        self.assertEqual(status, 200)
        names = json.loads(data)
        self.assertIn("mixed-wave.json", names)
