from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stagelane.cli import main


class CliTests(unittest.TestCase):
    def test_presets_lists_yards(self) -> None:
        self.assertEqual(main(["presets"]), 0)

    def test_seat_json_round_trip(self) -> None:
        example = Path(__file__).resolve().parents[1] / "examples" / "clear-yard.json"
        code = main(["seat", str(example), "--json"])
        self.assertEqual(code, 0)

    def test_leftover_pallets_use_exit_code_two(self) -> None:
        example = Path(__file__).resolve().parents[1] / "examples" / "temp-block.json"
        self.assertEqual(main(["seat", str(example)]), 2)

    def test_strategy_override_still_seats_clear_yard(self) -> None:
        example = Path(__file__).resolve().parents[1] / "examples" / "clear-yard.json"
        self.assertEqual(main(["seat", str(example), "--strategy", "cluster"]), 0)

    def test_unknown_temp_uses_exit_code_two(self) -> None:
        payload = {
            "yard": {"preset": "chill"},
            "pallets": [
                {
                    "id": "DRY",
                    "carrier": "UPS",
                    "temp": "dry",
                    "length_mm": 1200,
                    "width_mm": 1000,
                    "height_mm": 1400,
                    "weight_kg": 200,
                }
            ],
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(payload, handle)
            path = handle.name
        self.assertEqual(main(["seat", path]), 2)
