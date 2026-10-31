from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cartclip.cli import main

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


class CliTests(unittest.TestCase):
    def test_presets_lists_floors_and_carts(self) -> None:
        self.assertEqual(main(["presets"]), 0)

    def test_clip_json_round_trip(self) -> None:
        code = main(["clip", str(EXAMPLES / "mixed-wave.json"), "--json"])
        self.assertEqual(code, 0)

    def test_leftover_orders_use_exit_code_two(self) -> None:
        self.assertEqual(main(["clip", str(EXAMPLES / "too-heavy.json")]), 2)

    def test_strategy_override_changes_clustering(self) -> None:
        payload = json.loads((EXAMPLES / "aisle-cluster.json").read_text())
        payload["strategy"] = "auto"
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(payload, handle)
            path = handle.name
        self.assertEqual(main(["clip", path, "--strategy", "aisle"]), 0)
