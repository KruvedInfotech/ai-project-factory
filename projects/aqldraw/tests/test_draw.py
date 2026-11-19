from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aqldraw.cards import accept_number, letter_for, sample_size
from aqldraw.draw import draw_indices, plan, switching_advice
from aqldraw.model import Receipt


EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def load_example(name: str) -> Receipt:
    payload = json.loads((EXAMPLES / name).read_text(encoding="utf-8"))
    return Receipt.from_dict(payload)


def by_sku(result, sku: str):
    return next(item for item in result.lots if item.sku == sku)


def class_named(lot, name: str):
    return next(item for item in lot.classes if item.name == name)


class LetterTests(unittest.TestCase):
    def test_level_ii_bands(self) -> None:
        self.assertEqual(letter_for(1, "II", "normal"), "A")
        self.assertEqual(letter_for(8, "II", "normal"), "A")
        self.assertEqual(letter_for(12, "II", "normal"), "B")
        self.assertEqual(letter_for(90, "II", "normal"), "E")
        self.assertEqual(letter_for(500, "II", "normal"), "H")
        self.assertEqual(letter_for(501, "II", "normal"), "J")
        self.assertEqual(letter_for(2000, "II", "normal"), "K")

    def test_level_slides_letter(self) -> None:
        self.assertEqual(letter_for(500, "I", "normal"), "G")
        self.assertEqual(letter_for(500, "III", "normal"), "J")

    def test_severity_slides_letter(self) -> None:
        self.assertEqual(letter_for(500, "II", "tightened"), "J")
        self.assertEqual(letter_for(500, "II", "reduced"), "G")

    def test_spot_check_is_much_smaller(self) -> None:
        self.assertEqual(letter_for(2000, "S-2", "normal"), "D")
        n, _ = sample_size("D", 2000)
        self.assertEqual(n, 8)
        k, _ = sample_size(letter_for(2000, "II", "normal"), 2000)
        self.assertEqual(k, 125)

    def test_sample_caps_at_lot_size(self) -> None:
        n, hundred = sample_size("A", 2)
        self.assertEqual(n, 2)
        self.assertTrue(hundred)
        n, hundred = sample_size("H", 500)
        self.assertEqual(n, 50)
        self.assertFalse(hundred)


class AcceptTests(unittest.TestCase):
    def test_zero_tolerance_is_ac_zero(self) -> None:
        self.assertEqual(accept_number(50, 0), 0)

    def test_known_screens(self) -> None:
        self.assertEqual(accept_number(50, 0.65), 1)
        self.assertEqual(accept_number(50, 2.5), 3)
        self.assertEqual(accept_number(50, 6.5), 6)
        self.assertEqual(accept_number(3, 0.65), 0)
        self.assertEqual(accept_number(13, 2.5), 1)

    def test_reject_is_ac_plus_one(self) -> None:
        ac = accept_number(50, 2.5)
        lot = by_sku(plan(load_example("inbound-pass.json")), "CARTON-A")
        self.assertEqual(class_named(lot, "major").re, ac + 1)


class DrawTests(unittest.TestCase):
    def test_indices_are_unique_sorted_and_in_range(self) -> None:
        drawn = draw_indices(500, 50, "ASN-4418|CARTON-A|H|50")
        self.assertEqual(len(drawn), 50)
        self.assertEqual(drawn, sorted(drawn))
        self.assertEqual(len(set(drawn)), 50)
        self.assertEqual(drawn[0], min(drawn))
        self.assertGreaterEqual(drawn[0], 1)
        self.assertLessEqual(drawn[-1], 500)

    def test_same_seed_is_stable(self) -> None:
        a = draw_indices(90, 13, "seed-a")
        b = draw_indices(90, 13, "seed-a")
        self.assertEqual(a, b)

    def test_different_seed_changes_the_draw(self) -> None:
        a = draw_indices(90, 13, "seed-a")
        b = draw_indices(90, 13, "seed-b")
        self.assertNotEqual(a, b)


class PlanTests(unittest.TestCase):
    def test_inbound_pass_accepts_both_lots(self) -> None:
        result = plan(load_example("inbound-pass.json"))
        self.assertTrue(result.all_accept)
        self.assertEqual(result.reject_count, 0)
        self.assertEqual(result.switching, "stay")
        carton = by_sku(result, "CARTON-A")
        self.assertEqual(carton.letter, "H")
        self.assertEqual(carton.sample_size, 50)
        self.assertEqual(carton.verdict, "accept")
        self.assertEqual(class_named(carton, "critical").ac, 1)
        self.assertEqual(class_named(carton, "major").ac, 3)
        self.assertEqual(class_named(carton, "minor").ac, 6)
        tape = by_sku(result, "TAPE-9")
        self.assertEqual(tape.letter, "E")
        self.assertEqual(tape.sample_size, 13)
        self.assertEqual(tape.verdict, "accept")
        self.assertEqual(result.sample_total, 63)

    def test_inbound_reject_fails_on_major(self) -> None:
        result = plan(load_example("inbound-reject.json"))
        self.assertFalse(result.all_accept)
        carton = by_sku(result, "CARTON-A")
        self.assertEqual(carton.verdict, "reject")
        self.assertEqual(class_named(carton, "major").found, 4)
        self.assertEqual(class_named(carton, "major").ac, 3)
        self.assertEqual(class_named(carton, "major").verdict, "reject")
        self.assertEqual(class_named(carton, "critical").verdict, "accept")
        self.assertEqual(result.switching, "stay")

    def test_small_lot_one_critical_rejects(self) -> None:
        result = plan(load_example("small-lot.json"))
        kit = by_sku(result, "KIT-MINI")
        self.assertEqual(kit.letter, "B")
        self.assertEqual(kit.sample_size, 3)
        self.assertEqual(class_named(kit, "critical").ac, 0)
        self.assertEqual(kit.verdict, "reject")

    def test_two_of_five_rejects_recommends_tighten(self) -> None:
        result = plan(load_example("switch-tighten.json"))
        self.assertEqual(result.reject_count, 1)
        self.assertEqual(result.switching, "tighten")

    def test_pending_when_found_omitted(self) -> None:
        receipt = Receipt.from_dict(
            {
                "receipt": "ASN-WAIT",
                "level": "II",
                "lots": [{"sku": "A", "lot_size": 500}],
            }
        )
        result = plan(receipt)
        self.assertEqual(result.pending_count, 1)
        self.assertFalse(result.all_accept)
        self.assertEqual(result.reject_count, 0)
        self.assertEqual(result.lots[0].verdict, "pending")

    def test_any_class_reject_fails_the_lot(self) -> None:
        receipt = Receipt.from_dict(
            {
                "receipt": "ASN-CRIT",
                "lots": [
                    {
                        "sku": "A",
                        "lot_size": 500,
                        "found": {"critical": 2, "major": 0, "minor": 0},
                    }
                ],
            }
        )
        result = plan(receipt)
        lot = result.lots[0]
        self.assertEqual(class_named(lot, "critical").ac, 1)
        self.assertEqual(lot.verdict, "reject")

    def test_tightened_uses_larger_sample(self) -> None:
        payload = json.loads((EXAMPLES / "inbound-pass.json").read_text(encoding="utf-8"))
        payload["severity"] = "tightened"
        payload["lots"] = [payload["lots"][0]]
        result = plan(Receipt.from_dict(payload))
        carton = result.lots[0]
        self.assertEqual(carton.letter, "J")
        self.assertEqual(carton.sample_size, 80)

    def test_found_over_sample_is_an_error(self) -> None:
        receipt = Receipt.from_dict(
            {
                "receipt": "ASN-BAD",
                "lots": [
                    {
                        "sku": "A",
                        "lot_size": 12,
                        "found": {"critical": 9, "major": 0, "minor": 0},
                    }
                ],
            }
        )
        with self.assertRaises(ValueError):
            plan(receipt)


class SwitchingTests(unittest.TestCase):
    def test_ten_accepts_on_normal_reduces(self) -> None:
        history = ["accept"] * 9
        self.assertEqual(switching_advice("normal", history, "accept"), "reduce")
        self.assertEqual(switching_advice("normal", history, None), "stay")

    def test_reduced_reject_returns_to_normal(self) -> None:
        self.assertEqual(switching_advice("reduced", ["accept"], "reject"), "return_to_normal")

    def test_five_accepts_on_tightened_returns(self) -> None:
        self.assertEqual(
            switching_advice("tightened", ["accept"] * 4, "accept"),
            "return_to_normal",
        )


class ModelTests(unittest.TestCase):
    def test_rejects_duplicate_skus(self) -> None:
        with self.assertRaises(ValueError):
            Receipt.from_dict(
                {
                    "receipt": "ASN-DUP",
                    "lots": [
                        {"sku": "A", "lot_size": 10},
                        {"sku": "A", "lot_size": 12},
                    ],
                }
            )

    def test_rejects_empty_receipt(self) -> None:
        with self.assertRaises(ValueError):
            Receipt.from_dict({"receipt": "ASN-EMPTY", "lots": []})

    def test_rejects_bad_history(self) -> None:
        with self.assertRaises(ValueError):
            Receipt.from_dict(
                {
                    "receipt": "ASN-H",
                    "history": ["maybe"],
                    "lots": [{"sku": "A", "lot_size": 10}],
                }
            )

    def test_default_classes_and_level(self) -> None:
        receipt = Receipt.from_dict(
            {"receipt": "ASN-DEF", "lots": [{"sku": "A", "lot_size": 10}]}
        )
        self.assertEqual(receipt.level, "II")
        self.assertEqual(receipt.severity, "normal")
        self.assertEqual(receipt.classes["critical"], 0.65)
        self.assertEqual(receipt.classes["major"], 2.5)


if __name__ == "__main__":
    unittest.main()
