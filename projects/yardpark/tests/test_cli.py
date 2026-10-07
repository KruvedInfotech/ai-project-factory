from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from yardpark.cli import main


class CliTests(unittest.TestCase):
    def test_presets_lists_yards(self) -> None:
        self.assertEqual(main(["presets"]), 0)

    def test_park_json_round_trip(self) -> None:
        example = Path(__file__).resolve().parents[1] / "examples" / "door-adjacent.json"
        code = main(["park", str(example), "--json"])
        self.assertEqual(code, 0)

    def test_leftover_uses_exit_code_two(self) -> None:
        example = Path(__file__).resolve().parents[1] / "examples" / "reefer-short.json"
        self.assertEqual(main(["park", str(example)]), 2)

    def test_clear_plan_is_zero(self) -> None:
        payload = {
            "yard": {"preset": "mini_6"},
            "trailers": [
                {
                    "id": "IN-1",
                    "kind": "inbound",
                    "temp": "dry",
                    "length_ft": 53,
                    "eta": "08:30",
                    "door": "D1",
                    "appointment": "10:00",
                }
            ],
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(payload, handle)
            path = handle.name
        self.assertEqual(main(["park", path]), 0)

    def test_strategy_override(self) -> None:
        example = Path(__file__).resolve().parents[1] / "examples" / "door-adjacent.json"
        self.assertEqual(main(["park", str(example), "--strategy", "auto"]), 0)
