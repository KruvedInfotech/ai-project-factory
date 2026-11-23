from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from hazpad.cli import main

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


class CliTests(unittest.TestCase):
    def test_classes_lists_the_grid(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(["classes"])
        self.assertEqual(code, 0)
        self.assertIn("Flammable liquid", buf.getvalue())
        self.assertIn("Mixing grid", buf.getvalue())

    def test_compatible_mix_exits_zero(self) -> None:
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(["check", str(EXAMPLES / "compatible-mix.json")]), 0)

    def test_oxidizer_clash_exits_two(self) -> None:
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(["check", str(EXAMPLES / "oxidizer-clash.json")]), 2)

    def test_json_round_trip(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(["check", str(EXAMPLES / "away-food.json"), "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(buf.getvalue())
        self.assertTrue(payload["all_fit"])
        self.assertEqual(payload["worst_code"], "A")

    def test_bad_file_exits_one(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            handle.write("{}")
            path = handle.name
        self.assertEqual(main(["check", path]), 1)
