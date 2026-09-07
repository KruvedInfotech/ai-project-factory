from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from loadfit.cli import main


class CliTests(unittest.TestCase):
    def test_presets_lists_trucks(self) -> None:
        self.assertEqual(main(["presets"]), 0)

    def test_pack_json_round_trip(self) -> None:
        example = Path(__file__).resolve().parents[1] / "examples" / "pallet-cases.json"
        code = main(["pack", str(example), "--json"])
        self.assertIn(code, (0, 2))

    def test_leftover_cartons_use_exit_code_two(self) -> None:
        payload = {
            "container": {"preset": "pallet_eu"},
            "boxes": [
                {
                    "sku": "HUGE",
                    "length_mm": 5000,
                    "width_mm": 5000,
                    "height_mm": 5000,
                    "weight_kg": 1,
                    "quantity": 1,
                }
            ],
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(payload, handle)
            path = handle.name
        self.assertEqual(main(["pack", path]), 2)
