from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from returnsort.cli import main


class CliTests(unittest.TestCase):
    def test_floors_lists_presets(self) -> None:
        self.assertEqual(main(["floors"]), 0)

    def test_plan_json_round_trip(self) -> None:
        example = Path(__file__).resolve().parents[1] / "examples" / "mixed-returns.json"
        code = main(["plan", str(example), "--json"])
        self.assertEqual(code, 0)

    def test_leftover_units_use_exit_code_two(self) -> None:
        payload = {
            "floor": {"preset": "store_backroom"},
            "labor_minutes": 8,
            "units": [
                {
                    "ticket": "R-HUGE",
                    "sku": "ICE-PACK",
                    "reason": "unwanted",
                    "grade": "sellable",
                    "temp": "freeze",
                    "quantity": 1,
                }
            ],
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(payload, handle)
            path = handle.name
        self.assertEqual(main(["plan", path]), 2)
