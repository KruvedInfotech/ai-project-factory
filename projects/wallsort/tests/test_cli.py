from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wallsort.cli import main

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


class CliTests(unittest.TestCase):
    def _run(self, argv: list[str]) -> tuple[int, str]:
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(argv)
        return code, buf.getvalue()

    def test_presets_lists_pack_wall(self) -> None:
        code, out = self._run(["presets"])
        self.assertEqual(code, 0)
        self.assertIn("wall_3x4", out)

    def test_sort_json_round_trip(self) -> None:
        code, out = self._run(["sort", str(EXAMPLES / "batch-wave.json"), "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertTrue(payload["all_fit"])
        self.assertEqual(payload["packed_count"], 10)

    def test_leftover_units_use_exit_code_two(self) -> None:
        code, _out = self._run(["sort", str(EXAMPLES / "too-big.json")])
        self.assertEqual(code, 2)

    def test_strategy_override_changes_fill_order(self) -> None:
        payload = json.loads((EXAMPLES / "batch-wave.json").read_text())
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(payload, handle)
            path = handle.name
        code, out = self._run(["sort", path, "--strategy", "carrier", "--json"])
        self.assertEqual(code, 0)
        result = json.loads(out)
        fedex = [item for item in result["orders"] if item["carrier"] == "FEDEX"]
        self.assertEqual([item["cubby"] for item in fedex], ["R1C1", "R1C2"])
