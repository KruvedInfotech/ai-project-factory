from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aislelock.cli import main


class CliTests(unittest.TestCase):
    def test_presets_lists_floors(self) -> None:
        self.assertEqual(main(["presets"]), 0)

    def test_lock_json_round_trip(self) -> None:
        example = Path(__file__).resolve().parents[1] / "examples" / "clear-wave.json"
        code = main(["lock", str(example), "--json"])
        self.assertEqual(code, 0)

    def test_leftover_carts_use_exit_code_two(self) -> None:
        example = Path(__file__).resolve().parents[1] / "examples" / "temp-block.json"
        self.assertEqual(main(["lock", str(example)]), 2)

    def test_strategy_override_still_locks_clear_wave(self) -> None:
        example = Path(__file__).resolve().parents[1] / "examples" / "clear-wave.json"
        self.assertEqual(main(["lock", str(example), "--strategy", "cluster"]), 0)

    def test_unknown_aisle_uses_exit_code_two(self) -> None:
        payload = {
            "floor": {"preset": "grocery"},
            "carts": [{"id": "LOST", "walk": [{"aisle": "Z", "picks": 1}]}],
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(payload, handle)
            path = handle.name
        self.assertEqual(main(["lock", path]), 2)
