from __future__ import annotations

import json
import sys
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from shipcut.server import Handler


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
        self.assertIn(b"ShipCut", data)

    def test_cards_api_lists_carriers(self) -> None:
        status, data = self._request("GET", "/api/cards")
        self.assertEqual(status, 200)
        body = json.loads(data)
        ids = [c["id"] for c in body["carriers"]]
        self.assertIn("metro_same", ids)
        self.assertIn("Z1", [z["id"] for z in body["zones"]])

    def test_check_api_returns_winner(self) -> None:
        payload = {
            "origin": "DC",
            "destination": "Store",
            "ready_at": "2026-11-17T10:30:00",
            "promised_on": "2026-11-17",
            "zone": "Z1",
            "pieces": [
                {
                    "sku": "KIT-A",
                    "length_cm": 30,
                    "width_cm": 20,
                    "height_cm": 12,
                    "weight_kg": 1.4,
                    "quantity": 2,
                }
            ],
        }
        status, data = self._request("POST", "/api/check", json.dumps(payload).encode())
        self.assertEqual(status, 200)
        result = json.loads(data)
        self.assertEqual(result["winner"], "metro_same")
        self.assertEqual(result["makes_sla_count"], 1)

    def test_bad_payload_is_400(self) -> None:
        status, data = self._request("POST", "/api/check", b"{}")
        self.assertEqual(status, 400)
        self.assertIn("error", json.loads(data))

    def test_distance_only_payload_maps_zone(self) -> None:
        payload = {
            "origin": "Ahmedabad DC",
            "destination": "Vadodara",
            "ready_at": "2026-11-17T17:10:00",
            "promised_on": "2026-11-18",
            "distance_km": 110,
            "pieces": [
                {
                    "sku": "CARTON-B",
                    "length_cm": 50,
                    "width_cm": 40,
                    "height_cm": 30,
                    "weight_kg": 8,
                    "quantity": 3,
                }
            ],
        }
        status, data = self._request("POST", "/api/check", json.dumps(payload).encode())
        self.assertEqual(status, 200)
        result = json.loads(data)
        self.assertEqual(result["zone"], "Z2")
        self.assertEqual(result["winner"], "night_run")

    def test_examples_list_and_fetch(self) -> None:
        status, data = self._request("GET", "/api/examples")
        self.assertEqual(status, 200)
        names = json.loads(data)
        self.assertIn("same-day.json", names)
        status, data = self._request("GET", "/api/examples/same-day.json")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(data)["zone"], "Z1")
