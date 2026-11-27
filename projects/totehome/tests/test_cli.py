from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from totehome.cli import main

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


class CliTests(unittest.TestCase):
    def test_totes_lists_std_and_wash(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(["totes"])
        self.assertEqual(code, 0)
        text = buf.getvalue().lower()
        self.assertIn("std", text)
        self.assertIn("wash", text)
        self.assertIn("nest", text)

    def test_plan_json_round_trip(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(["plan", str(EXAMPLES / "quiet-aisle.json"), "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(buf.getvalue())
        self.assertTrue(payload["all_fit"])
        self.assertEqual(payload["collected"], 20)
        self.assertEqual(payload["trip_count"], 1)

    def test_leftover_uses_exit_code_two(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(["plan", str(EXAMPLES / "shift-short.json")])
        self.assertEqual(code, 2)
        self.assertIn("FAR", buf.getvalue())

    def test_bad_json_uses_exit_code_one(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            handle.write("{")
            path = handle.name
        err = io.StringIO()
        with redirect_stderr(err):
            code = main(["plan", path])
        self.assertEqual(code, 1)
        self.assertIn("totehome:", err.getvalue())

    def test_opportunistic_still_exits_zero(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(["plan", str(EXAMPLES / "opportunistic.json")])
        self.assertEqual(code, 0)
        self.assertIn("PACK-LOW", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
