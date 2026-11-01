from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from palmix.cli import main


class CliTests(unittest.TestCase):
    def test_presets_lists_decks(self) -> None:
        self.assertEqual(main(["presets"]), 0)

    def test_mix_json_round_trip(self) -> None:
        example = Path(__file__).resolve().parents[1] / "examples" / "mixed-stores.json"
        code = main(["mix", str(example), "--json"])
        self.assertEqual(code, 0)

    def test_leftover_cases_use_exit_code_two(self) -> None:
        example = Path(__file__).resolve().parents[1] / "examples" / "too-heavy.json"
        self.assertEqual(main(["mix", str(example)]), 2)

    def test_strategy_override_keeps_store_groups(self) -> None:
        example = Path(__file__).resolve().parents[1] / "examples" / "store-lock.json"
        self.assertEqual(main(["mix", str(example), "--strategy", "store"]), 0)

    def test_bad_json_file_uses_exit_code_one_path(self) -> None:
        payload = {
            "deck": {"preset": "gma_48"},
            "cases": [
                {
                    "sku": "HUGE",
                    "store": "01",
                    "family": "bulk",
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
        self.assertEqual(main(["mix", path]), 2)
