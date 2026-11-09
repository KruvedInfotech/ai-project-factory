from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from taskweave.cli import main


class CliTests(unittest.TestCase):
    def test_presets_lists_floors(self) -> None:
        self.assertEqual(main(["presets"]), 0)

    def test_weave_json_round_trip(self) -> None:
        example = Path(__file__).resolve().parents[1] / "examples" / "clear-board.json"
        code = main(["weave", str(example), "--json"])
        self.assertEqual(code, 0)

    def test_leftover_tasks_use_exit_code_two(self) -> None:
        example = Path(__file__).resolve().parents[1] / "examples" / "labor-capped.json"
        self.assertEqual(main(["weave", str(example)]), 2)

    def test_strategy_override_still_weaves_clear_board(self) -> None:
        example = Path(__file__).resolve().parents[1] / "examples" / "clear-board.json"
        self.assertEqual(main(["weave", str(example), "--strategy", "nearest"]), 0)

    def test_unknown_temp_uses_exit_code_two(self) -> None:
        payload = {
            "floor": {"preset": "produce"},
            "tasks": [
                {
                    "id": "DRY",
                    "kind": "putaway",
                    "from": "C1",
                    "to": "A1-1",
                    "temp": "dry",
                    "pallets": 1,
                    "weight_kg": 200,
                    "height_mm": 1200,
                }
            ],
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(payload, handle)
            path = handle.name
        self.assertEqual(main(["weave", path]), 2)
