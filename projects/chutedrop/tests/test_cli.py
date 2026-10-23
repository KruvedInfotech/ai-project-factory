from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chutedrop.cli import main

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


class CliTests(unittest.TestCase):
    def _run(self, argv: list[str]) -> tuple[int, str]:
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(argv)
        return code, buf.getvalue()

    def test_presets_lists_sorter_bank(self) -> None:
        code, out = self._run(["presets"])
        self.assertEqual(code, 0)
        self.assertIn("bank_2x5", out)

    def test_plan_json_round_trip(self) -> None:
        code, out = self._run(["plan", str(EXAMPLES / "store-wave.json"), "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertTrue(payload["all_fit"])
        self.assertEqual(payload["packed_cartons"], 14)

    def test_leftover_cartons_use_exit_code_two(self) -> None:
        code, _out = self._run(["plan", str(EXAMPLES / "too-big.json")])
        self.assertEqual(code, 2)

    def test_strategy_override_changes_fill_order(self) -> None:
        payload = json.loads((EXAMPLES / "store-wave.json").read_text())
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(payload, handle)
            path = handle.name
        code, out = self._run(["plan", path, "--strategy", "dest", "--json"])
        self.assertEqual(code, 0)
        result = json.loads(out)
        first_of = {}
        for item in result["dests"]:
            first_of[item["dest"]] = item["chutes"][0]
        self.assertEqual(first_of["STORE-04"], "R1C1")
        self.assertEqual(first_of["STORE-08"], "R1C2")
        self.assertEqual(first_of["STORE-12"], "R1C3")
