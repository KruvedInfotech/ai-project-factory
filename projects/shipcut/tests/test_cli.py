from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from shipcut.cli import main


EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


class CliTests(unittest.TestCase):
    def test_cards_lists_carriers(self) -> None:
        self.assertEqual(main(["cards"]), 0)

    def test_check_json_round_trip(self) -> None:
        code = main(["check", str(EXAMPLES / "same-day.json"), "--json"])
        self.assertEqual(code, 0)

    def test_same_day_example_exits_zero(self) -> None:
        self.assertEqual(main(["check", str(EXAMPLES / "same-day.json")]), 0)

    def test_too_late_uses_exit_code_two(self) -> None:
        self.assertEqual(main(["check", str(EXAMPLES / "too-late.json")]), 2)

    def test_bad_json_uses_exit_code_one(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            handle.write("{")
            path = handle.name
        self.assertEqual(main(["check", path]), 1)

    def test_missing_fields_use_exit_code_one(self) -> None:
        payload = {"pieces": []}
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(payload, handle)
            path = handle.name
        self.assertEqual(main(["check", path]), 1)
