from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from hazpad.matrix import CLASSES, ease_code, lookup, mix, worse


class MatrixTests(unittest.TestCase):
    def test_flammable_and_oxidizer_are_forbidden(self) -> None:
        self.assertEqual(lookup("3", "5.1"), "X")
        self.assertEqual(lookup("5.1", "3"), "X")

    def test_food_and_corrosive_are_forbidden(self) -> None:
        self.assertEqual(lookup("FOOD", "8"), "X")
        self.assertEqual(lookup("6.1", "FOOD"), "X")

    def test_same_class_oxidizers_are_away(self) -> None:
        self.assertEqual(lookup("5.1", "5.1"), "A")
        self.assertEqual(lookup("3", "3"), "C")

    def test_flammable_gas_and_toxic_gas_are_separated(self) -> None:
        self.assertEqual(lookup("2.1", "2.3"), "S")

    def test_paint_and_batteries_are_compatible(self) -> None:
        self.assertEqual(lookup("3", "9"), "C")

    def test_grid_is_square_and_symmetric(self) -> None:
        for a in CLASSES:
            for b in CLASSES:
                self.assertEqual(lookup(a, b), lookup(b, a), f"{a} vs {b}")

    def test_lq_eases_oxidizer_clash_to_separated(self) -> None:
        eased = mix("3", "5.1", both_limited=True)
        self.assertEqual(eased.raw, "X")
        self.assertEqual(eased.code, "S")
        self.assertTrue(eased.eased)

    def test_lq_does_not_ease_toxic_gas(self) -> None:
        self.assertEqual(ease_code("X", "2.3", "5.1", True), "X")

    def test_worse_prefers_forbidden(self) -> None:
        self.assertEqual(worse("A", "X"), "X")
        self.assertEqual(worse("C", "S"), "S")

    def test_unknown_class_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            lookup("1.1", "3")


if __name__ == "__main__":
    unittest.main()
