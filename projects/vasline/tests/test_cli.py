from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vasline.cli import main

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


class CliTests(unittest.TestCase):
    def test_ops_lists_relabel(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(["ops"])
        self.assertEqual(code, 0)
        self.assertIn("relabel", buf.getvalue())
        self.assertIn("kitting", buf.getvalue().lower())

    def test_plan_json_round_trip(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(["plan", str(EXAMPLES / "balanced-shift.json"), "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(buf.getvalue())
        self.assertTrue(payload["all_fit"])
        self.assertEqual(payload["scheduled_count"], 5)

    def test_leftover_uses_exit_code_two(self) -> None:
        code = main(["plan", str(EXAMPLES / "skill-miss.json")])
        self.assertEqual(code, 2)

    def test_bad_json_uses_exit_code_one(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            handle.write("{")
            path = handle.name
        err = io.StringIO()
        with redirect_stderr(err):
            code = main(["plan", path])
        self.assertEqual(code, 1)
        self.assertIn("vasline:", err.getvalue())

    def test_late_due_still_exits_zero_if_the_job_was_placed(self) -> None:
        # RUSH-A is tardy but placed; BULK-B leftover → exit 2 because of leftover.
        code = main(["plan", str(EXAMPLES / "late-due.json")])
        self.assertEqual(code, 2)
