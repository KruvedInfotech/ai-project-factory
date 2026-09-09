from __future__ import annotations

import json
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pickpath.cli import main


class CliTests(unittest.TestCase):
    def test_presets_lists_layouts(self) -> None:
        with patch("sys.stdout", new=StringIO()) as out:
            self.assertEqual(main(["presets"]), 0)
            self.assertIn("grocery_6x20", out.getvalue())

    def test_route_json_round_trip(self) -> None:
        example = Path(__file__).resolve().parents[1] / "examples" / "single-aisle.json"
        with patch("sys.stdout", new=StringIO()) as out:
            code = main(["route", str(example), "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["routed_count"], 3)
        self.assertTrue(payload["all_routed"])

    def test_strategy_override(self) -> None:
        example = Path(__file__).resolve().parents[1] / "examples" / "grocery-wave.json"
        with patch("sys.stdout", new=StringIO()) as out:
            code = main(["route", str(example), "--strategy", "return", "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["chosen_strategy"], "return")

    def test_skipped_picks_use_exit_code_two(self) -> None:
        example = Path(__file__).resolve().parents[1] / "examples" / "skipped-bay.json"
        self.assertEqual(main(["route", str(example)]), 2)

    def test_text_report_mentions_comparison(self) -> None:
        example = Path(__file__).resolve().parents[1] / "examples" / "single-aisle.json"
        with patch("sys.stdout", new=StringIO()) as out:
            main(["route", str(example)])
        text = out.getvalue()
        self.assertIn("PickPath", text)
        self.assertIn("Strategy comparison", text)

    def test_bad_json_file(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            handle.write("{}")
            path = handle.name
        self.assertRaises((ValueError, SystemExit), lambda: main(["route", path]))
