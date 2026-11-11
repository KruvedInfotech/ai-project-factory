from __future__ import annotations

import json
import sys
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from crewcut.server import Handler


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
        self.assertIn(b"CrewCut", data)

    def test_presets_include_sites_and_strategies(self) -> None:
        status, data = self._request("GET", "/api/presets")
        self.assertEqual(status, 200)
        payload = json.loads(data)
        ids = {row["id"] for row in payload["sites"]}
        self.assertIn("grocery", ids)
        self.assertIn("auto", payload["strategies"])

    def test_staff_api_returns_seats(self) -> None:
        payload = {
            "site": {"preset": "grocery"},
            "demand": [{"hour": 8, "skill": "pick", "heads": 1, "temp": "dry"}],
            "crew": [
                {
                    "id": "A-12",
                    "name": "Rivera",
                    "kind": "regular",
                    "skills": ["pick"],
                    "rate_per_hour": 18,
                    "available_start": 8,
                    "available_end": 14,
                    "temp": "dry",
                }
            ],
        }
        status, data = self._request("POST", "/api/staff", json.dumps(payload).encode())
        self.assertEqual(status, 200)
        result = json.loads(data)
        self.assertEqual(result["seated_count"], 1)
        self.assertTrue(result["all_fit"])

    def test_bad_payload_is_400(self) -> None:
        status, data = self._request("POST", "/api/staff", b"{}")
        self.assertEqual(status, 400)
        self.assertIn("error", json.loads(data))

    def test_examples_list_includes_clear_board(self) -> None:
        status, data = self._request("GET", "/api/examples")
        self.assertEqual(status, 200)
        names = json.loads(data)
        self.assertIn("clear-board.json", names)
        status, data = self._request("GET", "/api/examples/clear-board.json")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(data)["site"]["preset"], "grocery")
