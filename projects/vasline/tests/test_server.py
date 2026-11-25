from __future__ import annotations

import json
import sys
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vasline.server import Handler

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "balanced-shift.json"


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
        self.assertIn(b"VasLine", data)

    def test_ops_api_lists_catalog(self) -> None:
        status, data = self._request("GET", "/api/ops")
        self.assertEqual(status, 200)
        payload = json.loads(data)
        ids = [item["id"] for item in payload["ops"]]
        self.assertIn("relabel", ids)
        self.assertIn("kit", ids)

    def test_plan_api_returns_tasks(self) -> None:
        payload = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        status, data = self._request("POST", "/api/plan", json.dumps(payload).encode())
        self.assertEqual(status, 200)
        result = json.loads(data)
        self.assertEqual(result["scheduled_count"], 5)
        self.assertTrue(result["all_fit"])
        self.assertGreater(len(result["tasks"]), 0)

    def test_examples_list_and_fetch(self) -> None:
        status, data = self._request("GET", "/api/examples")
        self.assertEqual(status, 200)
        names = json.loads(data)
        self.assertIn("balanced-shift.json", names)
        status, data = self._request("GET", "/api/examples/balanced-shift.json")
        self.assertEqual(status, 200)
        self.assertIn("ORD-101", json.loads(data)["jobs"][0]["id"])

    def test_bad_payload_is_400(self) -> None:
        status, data = self._request("POST", "/api/plan", b"{}")
        self.assertEqual(status, 400)
        self.assertIn("error", json.loads(data))
