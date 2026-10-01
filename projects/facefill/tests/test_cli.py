from __future__ import annotations

import json
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from facefill.cli import main


class CliTests(unittest.TestCase):
    def test_presets_lists_warehouses(self) -> None:
        buf = StringIO()
        with patch("sys.stdout", buf):
            self.assertEqual(main(["presets"]), 0)
        text = buf.getvalue()
        self.assertIn("grocery_6", text)
        self.assertIn("mini_3", text)

    def test_fill_json_round_trip(self) -> None:
        example = Path(__file__).resolve().parents[1] / "examples" / "morning-grocery.json"
        buf = StringIO()
        with patch("sys.stdout", buf):
            code = main(["fill", str(example), "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(buf.getvalue())
        self.assertTrue(payload["all_filled"])
        self.assertEqual(payload["task_count"], 5)

    def test_leftover_faces_use_exit_code_two(self) -> None:
        example = Path(__file__).resolve().parents[1] / "examples" / "reserve-short.json"
        self.assertEqual(main(["fill", str(example)]), 2)

    def test_strategy_override_keeps_valid_exit(self) -> None:
        example = Path(__file__).resolve().parents[1] / "examples" / "morning-grocery.json"
        self.assertEqual(main(["fill", str(example), "--strategy", "cluster"]), 0)

    def test_text_report_mentions_tasks(self) -> None:
        example = Path(__file__).resolve().parents[1] / "examples" / "wave-breach.json"
        buf = StringIO()
        with patch("sys.stdout", buf):
            self.assertEqual(main(["fill", str(example)]), 0)
        self.assertIn("FaceFill", buf.getvalue())
        self.assertIn("E3-PEN", buf.getvalue())

    def test_bad_payload_raises_to_caller(self) -> None:
        payload = {"warehouse": {"preset": "mini_3"}, "faces": []}
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(payload, handle)
            path = handle.name
        with self.assertRaises(ValueError):
            main(["fill", path])
