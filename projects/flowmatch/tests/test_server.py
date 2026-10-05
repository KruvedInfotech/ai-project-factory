from __future__ import annotations

import json
import sys
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from flowmatch.server import Handler


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
        self.assertIn(b"FlowMatch", data)

    def test_presets_and_examples(self) -> None:
        status, data = self._request("GET", "/api/presets")
        self.assertEqual(status, 200)
        names = {item["id"] for item in json.loads(data)}
        self.assertIn("fmcg_6", names)
        status, data = self._request("GET", "/api/examples")
        self.assertEqual(status, 200)
        self.assertIn("grocery-same-day.json", json.loads(data))

    def test_match_api_returns_allocations(self) -> None:
        payload = {
            "yard": {"preset": "mini_3"},
            "receipts": [
                {"id": "IN-1", "sku": "SKU-A", "pallets": 2, "eta": "08:30", "door": "D1", "temp": "dry"}
            ],
            "orders": [
                {"id": "OUT-1", "sku": "SKU-A", "pallets": 2, "cutoff": "11:00", "door": "D1", "temp": "dry"}
            ],
        }
        status, data = self._request("POST", "/api/match", json.dumps(payload).encode())
        self.assertEqual(status, 200)
        result = json.loads(data)
        self.assertTrue(result["all_clear"])
        self.assertEqual(result["allocations"][0]["sku"], "SKU-A")
        self.assertEqual(result["allocations"][0]["mode"], "live")

    def test_bad_payload_is_400(self) -> None:
        status, data = self._request("POST", "/api/match", b"{}")
        self.assertEqual(status, 400)
        self.assertIn("error", json.loads(data))
