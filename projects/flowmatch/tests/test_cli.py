from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from flowmatch.cli import main


class CliTests(unittest.TestCase):
    def test_presets_lists_yards(self) -> None:
        self.assertEqual(main(["presets"]), 0)

    def test_match_json_round_trip(self) -> None:
        example = Path(__file__).resolve().parents[1] / "examples" / "live-unload.json"
        code = main(["match", str(example), "--json"])
        self.assertEqual(code, 0)

    def test_leftover_uses_exit_code_two(self) -> None:
        example = Path(__file__).resolve().parents[1] / "examples" / "reefer-short.json"
        self.assertEqual(main(["match", str(example)]), 2)

    def test_clear_plan_is_zero(self) -> None:
        payload = {
            "yard": {"preset": "mini_3"},
            "receipts": [
                {"id": "IN-1", "sku": "SKU-A", "pallets": 2, "eta": "08:30", "door": "D1", "temp": "dry"}
            ],
            "orders": [
                {"id": "OUT-1", "sku": "SKU-A", "pallets": 2, "cutoff": "11:00", "door": "D1", "temp": "dry"}
            ],
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(payload, handle)
            path = handle.name
        self.assertEqual(main(["match", path]), 0)

    def test_strategy_override(self) -> None:
        example = Path(__file__).resolve().parents[1] / "examples" / "live-unload.json"
        self.assertEqual(main(["match", str(example), "--strategy", "lane"]), 0)
