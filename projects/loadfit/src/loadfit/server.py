"""Stdlib HTTP front-end for the packer."""

from __future__ import annotations

import json
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .containers import PRESETS
from .model import Shipment
from .pack import pack

STATIC_DIR = Path(__file__).resolve().parent / "static"
EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "examples"


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            self._send_file(STATIC_DIR / "index.html", "text/html; charset=utf-8")
            return
        if parsed.path == "/api/presets":
            body = [PRESETS[key].as_dict() | {"id": key} for key in sorted(PRESETS)]
            self._send_json(body)
            return
        if parsed.path.startswith("/api/examples/"):
            name = Path(parsed.path).name
            path = EXAMPLES_DIR / name
            if path.is_file() and path.suffix == ".json":
                self._send_file(path, "application/json")
                return
            self._send_json({"error": "example not found"}, 404)
            return
        if parsed.path == "/api/examples":
            names = sorted(p.name for p in EXAMPLES_DIR.glob("*.json")) if EXAMPLES_DIR.is_dir() else []
            self._send_json(names)
            return
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/api/pack":
            self._send_json({"error": "not found"}, 404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
            result = pack(Shipment.from_dict(payload))
        except (ValueError, KeyError, json.JSONDecodeError, TypeError) as exc:
            self._send_json({"error": str(exc)}, 400)
            return
        self._send_json(result.as_dict())

    def _send_json(self, payload: object, status: int = 200) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _send_file(self, path: Path, content_type: str) -> None:
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def serve(host: str, port: int) -> None:
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"LoadFit planner at http://{host}:{port}")
    httpd.serve_forever()
