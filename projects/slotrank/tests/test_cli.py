from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from slotrank.cli import main


class CliTests(unittest.TestCase):
    def test_presets_lists_warehouses(self) -> None:
        self.assertEqual(main(["presets"]), 0)

    def test_slot_json_round_trip(self) -> None:
        example = Path(__file__).resolve().parents[1] / "examples" / "mis-slotted-grocery.json"
        code = main(["slot", str(example), "--json"])
        self.assertIn(code, (0, 2))

    def test_leftover_uses_exit_code_two(self) -> None:
        payload = {
            "warehouse": {"preset": "mini_3"},
            "skus": [
                {
                    "sku": "EACH",
                    "picks": 10,
                    "cube": 2,
                    "weight_kg": 1,
                    "slot_type": "piece",
                }
            ],
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(payload, handle)
            path = handle.name
        self.assertEqual(main(["slot", path]), 2)

    def test_keep_only_plan_is_zero(self) -> None:
        payload = {
            "warehouse": {"preset": "mini_3"},
            "skus": [
                {
                    "sku": "MILK",
                    "picks": 20,
                    "cube": 8,
                    "weight_kg": 4,
                    "slot_type": "case",
                    "current": "A1-01",
                }
            ],
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(payload, handle)
            path = handle.name
        self.assertEqual(main(["slot", path]), 0)
