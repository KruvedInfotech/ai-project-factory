from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from putsteer.cli import main


class CliTests(unittest.TestCase):
    def test_presets_lists_policies(self) -> None:
        self.assertEqual(main(["presets"]), 0)

    def test_put_json_round_trip(self) -> None:
        example = Path(__file__).resolve().parents[1] / "examples" / "inbound-wave.json"
        self.assertEqual(main(["put", str(example), "--json"]), 0)

    def test_leftover_uses_exit_code_two(self) -> None:
        example = Path(__file__).resolve().parents[1] / "examples" / "height-cap.json"
        self.assertEqual(main(["put", str(example)]), 2)

    def test_clear_plan_is_zero(self) -> None:
        payload = {
            "policy": {"preset": "reserve_dc"},
            "inbound": [
                {
                    "id": "LPN-1",
                    "sku": "RICE",
                    "qty": 10,
                    "height_mm": 1200,
                    "weight_kg": 200,
                    "temp": "dry",
                    "velocity": "A",
                    "priority": 1,
                }
            ],
            "locations": [
                {
                    "id": "R-A-01-1",
                    "zone": "A",
                    "type": "reserve",
                    "aisle": 1,
                    "bay": 1,
                    "level": 1,
                    "temp": "dry",
                    "max_pallets": 1,
                    "max_height_mm": 1800,
                    "max_weight_kg": 1000,
                }
            ],
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(payload, handle)
            path = handle.name
        self.assertEqual(main(["put", path]), 0)

    def test_strategy_override(self) -> None:
        example = Path(__file__).resolve().parents[1] / "examples" / "inbound-wave.json"
        self.assertEqual(main(["put", str(example), "--strategy", "heavy"]), 0)
