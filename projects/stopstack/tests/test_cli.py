from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stopstack.cli import main

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


class CliTests(unittest.TestCase):
    def test_presets_lists_grocery(self) -> None:
        self.assertEqual(main(["presets"]), 0)

    def test_stack_json_round_trip(self) -> None:
        example = EXAMPLES / "milk-run.json"
        code = main(["stack", str(example), "--json"])
        self.assertEqual(code, 0)

    def test_leftover_pallets_use_exit_code_two(self) -> None:
        example = EXAMPLES / "payload-capped.json"
        self.assertEqual(main(["stack", str(example)]), 2)

    def test_strategy_override_changes_row_sharing(self) -> None:
        payload = json.loads((EXAMPLES / "milk-run.json").read_text())
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(payload, handle)
            path = handle.name
        self.assertEqual(main(["stack", path, "--strategy", "no-mix", "--json"]), 0)
