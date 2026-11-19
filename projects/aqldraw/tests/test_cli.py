from __future__ import annotations

import json
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aqldraw.cli import main


EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


class CliTests(unittest.TestCase):
    def test_cards_lists_levels(self) -> None:
        buf = StringIO()
        with patch("sys.stdout", buf):
            self.assertEqual(main(["cards"]), 0)
        out = buf.getvalue()
        self.assertIn("Level II", out)
        self.assertIn("H:50", out)

    def test_draw_json_round_trip(self) -> None:
        buf = StringIO()
        with patch("sys.stdout", buf):
            code = main(["draw", str(EXAMPLES / "inbound-pass.json"), "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(buf.getvalue())
        self.assertTrue(payload["all_accept"])
        self.assertEqual(payload["lots"][0]["letter"], "H")

    def test_reject_uses_exit_code_two(self) -> None:
        buf = StringIO()
        with patch("sys.stdout", buf):
            self.assertEqual(main(["draw", str(EXAMPLES / "inbound-reject.json")]), 2)
        self.assertIn("REJECT", buf.getvalue())

    def test_bad_file_is_exit_one(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            handle.write("{")
            path = handle.name
        self.assertEqual(main(["draw", path]), 1)
