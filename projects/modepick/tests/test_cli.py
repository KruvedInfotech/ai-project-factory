from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from modepick.cli import main


class CliTests(unittest.TestCase):
    def test_cards_lists_zones_and_trucks(self) -> None:
        self.assertEqual(main(["cards"]), 0)

    def test_quote_json_round_trip(self) -> None:
        example = Path(__file__).resolve().parents[1] / "examples" / "small-parcel.json"
        code = main(["quote", str(example), "--json"])
        self.assertEqual(code, 0)

    def test_no_feasible_mode_uses_exit_code_two(self) -> None:
        payload = {
            "distance_km": 100,
            "pieces": [
                {
                    "sku": "MACHINE",
                    "length_cm": 400,
                    "width_cm": 250,
                    "height_cm": 250,
                    "weight_kg": 13000,
                    "quantity": 1,
                }
            ],
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(payload, handle)
            path = handle.name
        self.assertEqual(main(["quote", path]), 2)

    def test_bad_file_is_exit_code_one(self) -> None:
        self.assertEqual(main(["quote", "/no/such/file.json"]), 1)
