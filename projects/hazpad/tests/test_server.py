from __future__ import annotations

import json
import sys
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from hazpad.server import Handler


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
        self.assertIn(b"HazPad", data)

    def test_classes_api_includes_matrix(self) -> None:
        status, data = self._request("GET", "/api/classes")
        self.assertEqual(status, 200)
        body = json.loads(data)
        self.assertIn("3", [item["id"] for item in body["classes"]])
        self.assertTrue(body["matrix"])

    def test_check_api_places_compatible_lots(self) -> None:
        payload = {
            "pad": {"id": "PAD", "bays": 4},
            "lots": [
                {"lot": "GAS", "un": "1203", "kg": 80},
                {"lot": "LI", "un": "3480", "kg": 20},
            ],
        }
        status, data = self._request("POST", "/api/check", json.dumps(payload).encode())
        self.assertEqual(status, 200)
        result = json.loads(data)
        self.assertTrue(result["all_fit"])
        self.assertEqual(result["placed_count"], 2)

    def test_bad_payload_is_400(self) -> None:
        status, data = self._request("POST", "/api/check", b"{}")
        self.assertEqual(status, 400)
        self.assertIn("error", json.loads(data))

    def test_examples_list_includes_clash(self) -> None:
        status, data = self._request("GET", "/api/examples")
        self.assertEqual(status, 200)
        names = json.loads(data)
        self.assertIn("oxidizer-clash.json", names)
