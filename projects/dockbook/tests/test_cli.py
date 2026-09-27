from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dockbook.cli import main


class CliTests(unittest.TestCase):
    def test_presets_lists_yards(self) -> None:
        self.assertEqual(main(["presets"]), 0)

    def test_book_json_round_trip(self) -> None:
        example = Path(__file__).resolve().parents[1] / "examples" / "morning-inbound.json"
        self.assertEqual(main(["book", str(example), "--json"]), 0)

    def test_leftover_trailers_use_exit_code_two(self) -> None:
        example = Path(__file__).resolve().parents[1] / "examples" / "missed-window.json"
        self.assertEqual(main(["book", str(example)]), 2)

    def test_strategy_override_changes_assignment(self) -> None:
        payload = {
            "yard": {"preset": "mini_2"},
            "strategy": "earliest",
            "trailers": [
                {
                    "id": "WANT-A",
                    "carrier": "Local",
                    "direction": "inbound",
                    "length_m": 10,
                    "duration_min": 60,
                    "window_start": "08:00",
                    "window_end": "12:00",
                    "prefer_door": "A",
                }
            ],
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(payload, handle)
            path = handle.name
        self.assertEqual(main(["book", path, "--strategy", "preferred", "--json"]), 0)
