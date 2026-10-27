from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from slotfold.cli import main


class CliTests(unittest.TestCase):
    def test_presets_lists_rooms(self) -> None:
        self.assertEqual(main(["presets"]), 0)

    def test_fold_json_round_trip(self) -> None:
        example = Path(__file__).resolve().parents[1] / "examples" / "same-aisle.json"
        code = main(["fold", str(example), "--json"])
        self.assertIn(code, (0, 2))

    def test_leftover_locations_use_exit_code_two(self) -> None:
        payload = {
            "warehouse": {"preset": "small_dc"},
            "labor_minutes": 4,
            "locations": [
                {
                    "aisle": "A",
                    "bay": 1,
                    "level": 1,
                    "sku": "A",
                    "qty": 2,
                    "max_qty": 10,
                    "kind": "reserve",
                    "locked": True,
                },
                {
                    "aisle": "A",
                    "bay": 4,
                    "level": 1,
                    "sku": "A",
                    "qty": 3,
                    "max_qty": 10,
                    "kind": "reserve",
                },
            ],
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(payload, handle)
            path = handle.name
        self.assertEqual(main(["fold", path]), 2)
