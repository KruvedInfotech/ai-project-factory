from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from recvbay.cli import main


class CliTests(unittest.TestCase):
    def test_presets_lists_docks(self) -> None:
        self.assertEqual(main(["presets"]), 0)

    def test_dock_json_round_trip(self) -> None:
        example = Path(__file__).resolve().parents[1] / "examples" / "clear-dock.json"
        code = main(["dock", str(example), "--json"])
        self.assertEqual(code, 0)

    def test_leftover_loads_use_exit_code_two(self) -> None:
        example = Path(__file__).resolve().parents[1] / "examples" / "dwell-block.json"
        self.assertEqual(main(["dock", str(example)]), 2)

    def test_strategy_override_still_docks_clear_board(self) -> None:
        example = Path(__file__).resolve().parents[1] / "examples" / "clear-dock.json"
        self.assertEqual(main(["dock", str(example), "--strategy", "cluster"]), 0)

    def test_unknown_temp_uses_exit_code_two(self) -> None:
        payload = {
            "dock": {"preset": "produce"},
            "loads": [
                {
                    "id": "DRY",
                    "vendor": "NESTLE",
                    "temp": "dry",
                    "pallets": 2,
                }
            ],
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(payload, handle)
            path = handle.name
        self.assertEqual(main(["dock", path]), 2)
