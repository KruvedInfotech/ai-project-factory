from __future__ import annotations

import json
import sys
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kitline.server import Handler


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
        self.assertIn(b"KitLine", data)

    def test_presets_and_examples(self) -> None:
        status, data = self._request("GET", "/api/presets")
        self.assertEqual(status, 200)
        names = {item["id"] for item in json.loads(data)}
        self.assertIn("cell_2x3", names)
        status, data = self._request("GET", "/api/examples")
        self.assertEqual(status, 200)
        self.assertIn("gift-wave.json", json.loads(data))

    def test_plan_api_returns_placements(self) -> None:
        payload = {
            "line": {"preset": "mini_1x3"},
            "strategy": "auto",
            "inventory": [{"sku": "TEE", "on_hand": 8}],
            "kits": [
                {
                    "sku": "STARTER",
                    "length_mm": 250,
                    "width_mm": 180,
                    "height_mm": 70,
                    "weight_kg": 0.5,
                    "temp": "ambient",
                    "bom": [{"sku": "TEE", "quantity": 1}],
                }
            ],
            "builds": [
                {"id": "WO-1", "kit_sku": "STARTER", "quantity": 2, "priority": 2}
            ],
        }
        status, data = self._request("POST", "/api/plan", json.dumps(payload).encode())
        self.assertEqual(status, 200)
        result = json.loads(data)
        self.assertTrue(result["all_fit"])
        self.assertEqual(result["placements"][0]["build_id"], "WO-1")
        self.assertEqual(result["placements"][0]["row"], 1)
        self.assertEqual(result["placements"][0]["col"], 2)

    def test_bad_payload_is_400(self) -> None:
        status, data = self._request("POST", "/api/plan", b"{}")
        self.assertEqual(status, 400)
        self.assertIn("error", json.loads(data))
