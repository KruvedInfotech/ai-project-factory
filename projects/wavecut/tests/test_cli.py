from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wavecut.cli import main


class CliTests(unittest.TestCase):
    def test_presets_lists_shifts(self) -> None:
        self.assertEqual(main(["presets"]), 0)

    def test_cut_json_round_trip(self) -> None:
        example = Path(__file__).resolve().parents[1] / "examples" / "morning-stores.json"
        code = main(["cut", str(example), "--json"])
        self.assertIn(code, (0, 2))

    def test_leftover_orders_use_exit_code_two(self) -> None:
        example = Path(__file__).resolve().parents[1] / "examples" / "missed-cutoff.json"
        self.assertEqual(main(["cut", str(example)]), 2)

    def test_strategy_override_keeps_valid_exit(self) -> None:
        example = Path(__file__).resolve().parents[1] / "examples" / "ecom-cutoff.json"
        self.assertEqual(main(["cut", str(example), "--strategy", "auto"]), 0)

    def test_bad_payload_raises_to_caller(self) -> None:
        payload = {"shift": {"preset": "mini_3"}, "orders": []}
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(payload, handle)
            path = handle.name
        with self.assertRaises(ValueError):
            main(["cut", path])
