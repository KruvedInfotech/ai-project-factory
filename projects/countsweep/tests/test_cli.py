from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from countsweep.cli import main

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


class CliTests(unittest.TestCase):
    def test_presets_lists_grocery(self) -> None:
        self.assertEqual(main(["presets"]), 0)

    def test_plan_json_round_trip(self) -> None:
        example = EXAMPLES / "due-wave.json"
        code = main(["plan", str(example), "--json"])
        self.assertEqual(code, 0)

    def test_leftover_faces_use_exit_code_two(self) -> None:
        example = EXAMPLES / "labor-capped.json"
        self.assertEqual(main(["plan", str(example)]), 2)

    def test_strategy_override_changes_order(self) -> None:
        payload = json.loads((EXAMPLES / "due-wave.json").read_text())
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(payload, handle)
            path = handle.name
        self.assertEqual(main(["plan", path, "--strategy", "abc", "--json"]), 0)
