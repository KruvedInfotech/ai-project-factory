from __future__ import annotations

import json
import sys
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from totehome.server import Handler

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


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
        self.assertIn(b"ToteHome", data)

    def test_totes_api_lists_types(self) -> None:
        status, data = self._request("GET", "/api/totes")
        self.assertEqual(status, 200)
        payload = json.loads(data)
        ids = {item["id"] for item in payload["totes"]}
        self.assertEqual(ids, {"std", "cold", "oversize"})

    def test_plan_api_returns_trips(self) -> None:
        payload = json.loads((EXAMPLES / "quiet-aisle.json").read_text(encoding="utf-8"))
        status, data = self._request("POST", "/api/plan", json.dumps(payload).encode())
        self.assertEqual(status, 200)
        result = json.loads(data)
        self.assertTrue(result["all_fit"])
        self.assertEqual(result["collected"], 20)
        self.assertEqual(result["trip_count"], 1)

    def test_bad_payload_is_400(self) -> None:
        status, data = self._request("POST", "/api/plan", b"{}")
        self.assertEqual(status, 400)
        self.assertIn("error", json.loads(data))


if __name__ == "__main__":
    unittest.main()
