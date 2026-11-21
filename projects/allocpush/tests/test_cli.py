from __future__ import annotations

import json
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from allocpush.cli import main


EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


class CliTests(unittest.TestCase):
    def test_policies_lists_grades(self) -> None:
        buf = StringIO()
        with patch("sys.stdout", buf):
            self.assertEqual(main(["policies"]), 0)
        out = buf.getvalue()
        self.assertIn("fair_share", out)
        self.assertIn("A  ×3", out)

    def test_push_json_round_trip(self) -> None:
        buf = StringIO()
        with patch("sys.stdout", buf):
            code = main(["push", str(EXAMPLES / "balanced-push.json"), "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(buf.getvalue())
        self.assertTrue(payload["all_filled"])
        self.assertEqual(payload["push_units"], 156)

    def test_short_stock_uses_exit_code_two(self) -> None:
        buf = StringIO()
        with patch("sys.stdout", buf):
            self.assertEqual(main(["push", str(EXAMPLES / "short-stock.json")]), 2)
        self.assertIn("short", buf.getvalue())
        self.assertIn("ST-01", buf.getvalue())

    def test_bad_file_is_exit_one(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            handle.write("{")
            path = handle.name
        self.assertEqual(main(["push", path]), 1)
