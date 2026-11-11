from __future__ import annotations

import json
import sys
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from crewcut.cli import main

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


class CliTests(unittest.TestCase):
    def test_presets_lists_sites(self) -> None:
        with patch("sys.stdout", StringIO()) as out:
            self.assertEqual(main(["presets"]), 0)
        text = out.getvalue()
        self.assertIn("grocery", text)
        self.assertIn("produce", text)

    def test_staff_json_round_trip(self) -> None:
        example = EXAMPLES / "clear-board.json"
        with patch("sys.stdout", StringIO()) as out:
            code = main(["staff", str(example), "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertTrue(payload["all_fit"])
        self.assertEqual(payload["seated_count"], 11)

    def test_leftover_uses_exit_code_two(self) -> None:
        example = EXAMPLES / "labor-capped.json"
        with patch("sys.stdout", StringIO()):
            self.assertEqual(main(["staff", str(example)]), 2)

    def test_strategy_flag_overrides_the_board(self) -> None:
        example = EXAMPLES / "overtime.json"
        with patch("sys.stdout", StringIO()) as out:
            code = main(["staff", str(example), "--strategy", "overtime", "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        hour_11 = next(seat for seat in payload["seats"] if seat["hour"] == 11)
        self.assertEqual(hour_11["associate_id"], "A-12")
        self.assertTrue(hour_11["ot"])

    def test_text_report_mentions_the_site(self) -> None:
        example = EXAMPLES / "clear-board.json"
        with patch("sys.stdout", StringIO()) as out:
            self.assertEqual(main(["staff", str(example)]), 0)
        self.assertIn("CrewCut", out.getvalue())
        self.assertIn("Rivera", out.getvalue())
