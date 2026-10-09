from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lotdraw.cli import main


class CliTests(unittest.TestCase):
    def test_presets_lists_policies(self) -> None:
        self.assertEqual(main(["presets"]), 0)

    def test_draw_json_round_trip(self) -> None:
        example = Path(__file__).resolve().parents[1] / "examples" / "grocery-wave.json"
        code = main(["draw", str(example), "--json"])
        self.assertEqual(code, 0)

    def test_leftover_uses_exit_code_two(self) -> None:
        example = Path(__file__).resolve().parents[1] / "examples" / "short-life.json"
        self.assertEqual(main(["draw", str(example)]), 2)

    def test_clear_plan_is_zero(self) -> None:
        payload = {
            "policy": {"preset": "grocery_dc"},
            "today": "2026-10-09",
            "orders": [
                {
                    "id": "SO-1",
                    "sku": "MILK-1L",
                    "qty": 10,
                    "ship_by": "2026-10-10",
                    "priority": 1,
                }
            ],
            "lots": [
                {
                    "id": "L-1",
                    "sku": "MILK-1L",
                    "qty": 24,
                    "expiry": "2026-10-20",
                    "received": "2026-10-01",
                    "location": "A-1",
                }
            ],
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(payload, handle)
            path = handle.name
        self.assertEqual(main(["draw", path]), 0)

    def test_strategy_override(self) -> None:
        example = Path(__file__).resolve().parents[1] / "examples" / "grocery-wave.json"
        self.assertEqual(main(["draw", str(example), "--strategy", "fewest"]), 0)
