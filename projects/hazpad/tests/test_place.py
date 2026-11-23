from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from hazpad.model import Shipment
from hazpad.place import plan

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def load_example(name: str) -> Shipment:
    payload = json.loads((EXAMPLES / name).read_text(encoding="utf-8"))
    return Shipment.from_dict(payload)


class PlaceTests(unittest.TestCase):
    def test_compatible_mix_fills_front_bays(self) -> None:
        result = plan(load_example("compatible-mix.json"))
        self.assertTrue(result.all_fit)
        bays = {item.lot: item.bay for item in result.placements}
        self.assertEqual(bays["GAS-01"], 0)
        self.assertEqual(bays["LI-BATT"], 1)
        self.assertEqual(bays["N2-DEWAR"], 2)
        self.assertEqual(result.worst_code, "C")

    def test_oxidizer_is_left_off_a_gasoline_trailer(self) -> None:
        result = plan(load_example("oxidizer-clash.json"))
        self.assertFalse(result.all_fit)
        placed = {item.lot: item.bay for item in result.placements}
        self.assertEqual(placed["GAS-02"], 0)
        self.assertEqual(placed["EH-SOLID"], 1)
        self.assertEqual(result.leftover[0]["lot"], "H2O2-A")
        self.assertIn("GAS-02", result.leftover[0]["reason"])

    def test_food_keeps_an_empty_bay_from_paint(self) -> None:
        result = plan(load_example("away-food.json"))
        self.assertTrue(result.all_fit)
        bays = {item.lot: item.bay for item in result.placements}
        self.assertEqual(bays["PRODUCE"], 0)
        self.assertEqual(bays["PAINT-A"], 2)
        self.assertEqual(result.worst_code, "A")

    def test_toxic_gas_uses_the_rear_compartment(self) -> None:
        result = plan(load_example("two-compartment.json"))
        self.assertTrue(result.all_fit)
        by_lot = {item.lot: item for item in result.placements}
        self.assertEqual(by_lot["AERO-01"].bay, 0)
        self.assertEqual(by_lot["AERO-01"].compartment, 0)
        self.assertEqual(by_lot["TOXGAS-1"].bay, 3)
        self.assertEqual(by_lot["TOXGAS-1"].compartment, 1)
        self.assertEqual(result.worst_code, "S")

    def test_limited_qty_eases_oxidizer_to_a_partitioned_fit(self) -> None:
        result = plan(load_example("limited-qty.json"))
        self.assertTrue(result.all_fit)
        bays = {item.lot: item.bay for item in result.placements}
        self.assertEqual(bays["PAINT-LQ"], 0)
        self.assertEqual(bays["OX-LQ"], 2)
        pair = result.pairs[0]
        self.assertTrue(pair.eased)
        self.assertEqual(pair.raw_code, "X")
        self.assertEqual(pair.code, "S")

    def test_without_lq_ease_the_oxidizer_is_leftover(self) -> None:
        payload = json.loads((EXAMPLES / "limited-qty.json").read_text())
        payload["allow_limited_qty_ease"] = False
        result = plan(Shipment.from_dict(payload))
        self.assertFalse(result.all_fit)
        self.assertEqual(result.leftover[0]["lot"], "OX-LQ")

    def test_empty_bay_is_held_as_a_partition(self) -> None:
        result = plan(
            Shipment.from_dict(
                {
                    "pad": {
                        "id": "PAD",
                        "bays": 5,
                        "compartments": 1,
                        "empty_as_partition": True,
                    },
                    "lots": [
                        {"lot": "AERO", "class": "2.1", "kg": 100},
                        {"lot": "TOX", "class": "2.3", "kg": 90},
                        {"lot": "N2", "class": "2.2", "kg": 80},
                    ],
                }
            )
        )
        bays = {item.lot: item.bay for item in result.placements}
        self.assertEqual(bays["AERO"], 0)
        self.assertEqual(bays["TOX"], 2)
        self.assertNotEqual(bays["N2"], 1)
        self.assertTrue(result.all_fit)

    def test_food_flag_on_a_dg_lot_uses_the_worse_code(self) -> None:
        result = plan(
            Shipment.from_dict(
                {
                    "pad": {"id": "PAD", "bays": 4},
                    "lots": [
                        {"lot": "WINE", "class": "3", "kg": 200, "foodstuff": True},
                        {"lot": "BLEACH", "class": "8", "kg": 150},
                    ],
                }
            )
        )
        self.assertFalse(result.all_fit)
        self.assertEqual(result.leftover[0]["lot"], "BLEACH")
        self.assertEqual(result.pairs[0].code, "X")

    def test_heavier_lot_keeps_the_pad_when_codes_forbid_sharing(self) -> None:
        result = plan(
            Shipment.from_dict(
                {
                    "pad": {"id": "PAD", "bays": 3},
                    "lots": [
                        {"lot": "LIGHT-OX", "class": "5.1", "kg": 40},
                        {"lot": "HEAVY-GAS", "class": "3", "kg": 900},
                    ],
                }
            )
        )
        self.assertEqual(result.placements[0].lot, "HEAVY-GAS")
        self.assertEqual(result.leftover[0]["lot"], "LIGHT-OX")


class ModelTests(unittest.TestCase):
    def test_rejects_duplicate_lots(self) -> None:
        with self.assertRaises(ValueError):
            Shipment.from_dict(
                {
                    "pad": {"id": "PAD", "bays": 2},
                    "lots": [
                        {"lot": "A", "class": "3", "kg": 1},
                        {"lot": "A", "class": "9", "kg": 1},
                    ],
                }
            )

    def test_rejects_empty_shipment(self) -> None:
        with self.assertRaises(ValueError):
            Shipment.from_dict({"pad": {"id": "PAD", "bays": 2}, "lots": []})

    def test_known_un_fills_class(self) -> None:
        ship = Shipment.from_dict(
            {
                "pad": {"id": "PAD", "bays": 2},
                "lots": [{"lot": "G", "un": "1203", "kg": 10}],
            }
        )
        self.assertEqual(ship.lots[0].clazz, "3")
        self.assertEqual(ship.lots[0].description, "Gasoline")

    def test_compartment_split_on_even_bays(self) -> None:
        pad = Shipment.from_dict(
            {
                "pad": {"id": "VAN", "bays": 6, "compartments": 2},
                "lots": [{"lot": "A", "class": "9", "kg": 1}],
            }
        ).pad
        self.assertEqual(pad.compartment_of(0), 0)
        self.assertEqual(pad.compartment_of(2), 0)
        self.assertEqual(pad.compartment_of(3), 1)


if __name__ == "__main__":
    unittest.main()
