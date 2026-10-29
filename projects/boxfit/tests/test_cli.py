from __future__ import annotations

import json
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from boxfit.cli import main


class CliTests(unittest.TestCase):
    def test_presets_lists_catalogs(self) -> None:
        with patch("sys.stdout", new_callable=StringIO) as out:
            self.assertEqual(main(["presets"]), 0)
        text = out.getvalue()
        self.assertIn("ecom_pack", text)
        self.assertIn("parcel_dc", text)
        self.assertIn("grocery_shipper", text)

    def test_pack_json_round_trip(self) -> None:
        example = Path(__file__).resolve().parents[1] / "examples" / "mixed-order.json"
        with patch("sys.stdout", new_callable=StringIO) as out:
            code = main(["pack", str(example), "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertTrue(payload["all_fit"])
        self.assertGreaterEqual(payload["carton_count"], 1)

    def test_leftover_items_use_exit_code_two(self) -> None:
        example = Path(__file__).resolve().parents[1] / "examples" / "too-big.json"
        self.assertEqual(main(["pack", str(example)]), 2)

    def test_labor_capped_example_exits_two(self) -> None:
        example = Path(__file__).resolve().parents[1] / "examples" / "labor-capped.json"
        with patch("sys.stdout", new_callable=StringIO) as out:
            code = main(["pack", str(example), "--json"])
        self.assertEqual(code, 2)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["leftover"][0]["reason"], "labor cap")

    def test_invalid_json_file_is_usage_error(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump({"catalog": {"preset": "ecom_pack"}, "items": []}, handle)
            path = handle.name
        self.assertEqual(main(["pack", path]), 1)
