from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lastfree.cli import main

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


class CliTests(unittest.TestCase):
    def test_presets_lists_terminals(self) -> None:
        self.assertEqual(main(["presets"]), 0)

    def test_clock_json_round_trip_on_free_example(self) -> None:
        code = main(["clock", str(EXAMPLES / "still-inside.json"), "--json"])
        self.assertEqual(code, 0)

    def test_charges_use_exit_code_two(self) -> None:
        self.assertEqual(main(["clock", str(EXAMPLES / "gated-with-fees.json")]), 2)

    def test_bad_container_is_usage_error(self) -> None:
        payload = {
            "container": "NOPE",
            "preset": "uswc_port",
            "available_on": "2026-11-10",
            "as_of": "2026-11-12",
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(payload, handle)
            path = handle.name
        self.assertEqual(main(["clock", path]), 1)
