from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stopstack.model import Load
from stopstack.stack import stack

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def pal(**kwargs) -> dict:
    row = {
        "id": "PAL-1",
        "sku": "RICE",
        "weight_kg": 300,
        "height_mm": 1200,
        "temp": "dry",
    }
    row.update(kwargs)
    return row


def stop(**kwargs) -> dict:
    row = {"id": "S1", "seq": 1, "name": "Store 1", "pallets": [pal()]}
    row.update(kwargs)
    return row


def load(**kwargs) -> Load:
    payload = {
        "trailer": {"preset": "mini_6"},
        "strategy": "lifo",
        "stops": [stop()],
    }
    payload.update(kwargs)
    return Load.from_dict(payload)


class StackTests(unittest.TestCase):
    def test_single_pallet_sits_at_the_nose(self) -> None:
        result = stack(load())
        self.assertTrue(result.all_fit)
        placed = result.placements[0]
        self.assertEqual(placed.row, 1)
        self.assertEqual(placed.col, 1)
        self.assertEqual(placed.side, "L")
        self.assertEqual(placed.level, 0)

    def test_milk_run_puts_last_stop_in_the_nose(self) -> None:
        payload = json.loads((EXAMPLES / "milk-run.json").read_text())
        result = stack(Load.from_dict(payload))
        self.assertTrue(result.all_fit)
        self.assertEqual(result.packed_count, 8)
        self.assertEqual(result.labor_used_min, 24)
        by_id = {item.pallet_id: item for item in result.placements}
        self.assertEqual((by_id["PAL-S1"].row, by_id["PAL-S1"].side), (1, "L"))
        self.assertEqual((by_id["PAL-S2"].row, by_id["PAL-S2"].side), (1, "R"))
        self.assertEqual((by_id["PAL-S3"].row, by_id["PAL-S3"].side), (2, "L"))
        self.assertEqual((by_id["PAL-C1"].row, by_id["PAL-C1"].side), (2, "R"))
        self.assertEqual((by_id["PAL-N1"].row, by_id["PAL-N1"].side), (4, "L"))
        self.assertEqual((by_id["PAL-N2"].row, by_id["PAL-N2"].side), (4, "R"))
        south_rows = {item.row for item in result.placements if item.stop_id == "SOUTH"}
        north_rows = {item.row for item in result.placements if item.stop_id == "NORTH"}
        self.assertLess(max(south_rows), min(north_rows))

    def test_same_stop_stacks_two_high_before_a_new_row(self) -> None:
        result = stack(
            load(
                stops=[
                    stop(
                        pallets=[
                            pal(id="BASE", height_mm=1100, weight_kg=400),
                            pal(id="TOP", height_mm=1100, weight_kg=200),
                            pal(id="NEXT", height_mm=1100, weight_kg=300),
                        ]
                    )
                ]
            )
        )
        by_id = {item.pallet_id: item for item in result.placements}
        self.assertEqual((by_id["BASE"].row, by_id["BASE"].col, by_id["BASE"].level), (1, 1, 0))
        self.assertEqual((by_id["TOP"].row, by_id["TOP"].col, by_id["TOP"].level), (1, 1, 1))
        self.assertEqual((by_id["NEXT"].row, by_id["NEXT"].col, by_id["NEXT"].level), (1, 2, 0))

    def test_too_tall_pair_does_not_stack(self) -> None:
        result = stack(
            load(
                stops=[
                    stop(
                        pallets=[
                            pal(id="A", height_mm=1400),
                            pal(id="B", height_mm=1400),
                        ]
                    )
                ]
            )
        )
        by_id = {item.pallet_id: item for item in result.placements}
        self.assertEqual(by_id["A"].level, 0)
        self.assertEqual(by_id["B"].level, 0)
        self.assertEqual(by_id["B"].col, 2)

    def test_no_mix_keeps_a_row_to_one_stop(self) -> None:
        mixed = stack(
            load(
                strategy="lifo",
                stops=[
                    stop(id="FIRST", seq=1, name="First", pallets=[pal(id="F1")]),
                    stop(id="LAST", seq=2, name="Last", pallets=[pal(id="L1")]),
                ],
            )
        )
        no_mix = stack(
            load(
                strategy="no-mix",
                stops=[
                    stop(id="FIRST", seq=1, name="First", pallets=[pal(id="F1")]),
                    stop(id="LAST", seq=2, name="Last", pallets=[pal(id="L1")]),
                ],
            )
        )
        mixed_by = {item.pallet_id: item for item in mixed.placements}
        nomix_by = {item.pallet_id: item for item in no_mix.placements}
        self.assertEqual((mixed_by["L1"].row, mixed_by["L1"].col), (1, 1))
        self.assertEqual((mixed_by["F1"].row, mixed_by["F1"].col), (1, 2))
        self.assertEqual((nomix_by["L1"].row, nomix_by["L1"].col), (1, 1))
        self.assertEqual((nomix_by["F1"].row, nomix_by["F1"].col), (2, 1))

    def test_payload_cap_leaves_the_third_tiles_pallet(self) -> None:
        payload = json.loads((EXAMPLES / "payload-capped.json").read_text())
        result = stack(Load.from_dict(payload))
        self.assertEqual(result.packed_count, 2)
        self.assertEqual(result.weight_used_kg, 3600)
        self.assertEqual(result.leftover[0]["id"], "PAL-H3")
        self.assertEqual(result.leftover[0]["reason"], "payload")

    def test_labor_cap_leaves_the_first_drop(self) -> None:
        payload = json.loads((EXAMPLES / "labor-capped.json").read_text())
        result = stack(Load.from_dict(payload))
        self.assertEqual(result.packed_count, 3)
        self.assertEqual(result.labor_used_min, 6)
        self.assertEqual({item.pallet_id for item in result.placements}, {"PAL-L1", "PAL-L2", "PAL-L3"})
        self.assertEqual(result.leftover[0]["id"], "PAL-F1")
        self.assertEqual(result.leftover[0]["reason"], "labor-cap")

    def test_reefer_pallet_is_leftover_on_a_dry_box(self) -> None:
        payload = json.loads((EXAMPLES / "temp-mismatch.json").read_text())
        result = stack(Load.from_dict(payload))
        self.assertEqual(result.packed_count, 3)
        self.assertEqual(result.leftover[0]["id"], "PAL-R1")
        self.assertEqual(result.leftover[0]["reason"], "temp")
        packed_ids = [item.pallet_id for item in result.placements]
        self.assertEqual(packed_ids, ["PAL-D2", "PAL-D3", "PAL-D1"])

    def test_mixed_trailer_takes_reefer(self) -> None:
        result = stack(
            load(
                trailer={"preset": "mini_6"},
                stops=[stop(pallets=[pal(id="COLD", temp="reefer")])],
            )
        )
        self.assertTrue(result.all_fit)
        self.assertEqual(result.placements[0].temp, "reefer")

    def test_too_tall_pallet_never_boards(self) -> None:
        result = stack(load(stops=[stop(pallets=[pal(id="TOWER", height_mm=2500)])]))
        self.assertEqual(result.leftover[0]["reason"], "too-tall")
        self.assertEqual(result.packed_count, 0)

    def test_full_deck_leaves_no_slot(self) -> None:
        pallets = [pal(id=f"P{i}", height_mm=1800) for i in range(9)]
        result = stack(
            load(
                trailer={"preset": "city_van"},
                stops=[stop(pallets=pallets)],
            )
        )
        self.assertEqual(result.packed_count, 8)
        self.assertEqual(result.leftover[0]["id"], "P8")
        self.assertEqual(result.leftover[0]["reason"], "no-slot")

    def test_heavy_strategy_loads_the_heaviest_pallet_first(self) -> None:
        result = stack(
            load(
                strategy="heavy",
                stops=[
                    stop(
                        pallets=[
                            pal(id="LIGHT", weight_kg=100, height_mm=1100),
                            pal(id="HEAVY", weight_kg=500, height_mm=1100),
                        ]
                    )
                ]
            )
        )
        self.assertEqual(result.placements[0].pallet_id, "HEAVY")
        self.assertEqual(result.placements[0].level, 0)
        self.assertEqual(result.placements[1].pallet_id, "LIGHT")
        self.assertEqual(result.placements[1].level, 1)

    def test_quantity_expands_unique_ids(self) -> None:
        result = stack(
            load(stops=[stop(pallets=[pal(id="CASE", quantity=2, height_mm=1400)])])
        )
        ids = [item.pallet_id for item in result.placements]
        self.assertEqual(ids, ["CASE-1", "CASE-2"])

    def test_column_stop_seq_never_rises_toward_the_doors(self) -> None:
        payload = json.loads((EXAMPLES / "milk-run.json").read_text())
        result = stack(Load.from_dict(payload))
        by_col: dict[int, list[int]] = {}
        for item in result.placements:
            if item.level != 0:
                continue
            by_col.setdefault(item.col, []).append((item.row, item.stop_seq))
        for pairs in by_col.values():
            seqs = [seq for _, seq in sorted(pairs)]
            self.assertEqual(seqs, sorted(seqs, reverse=True))

    def test_duplicate_stop_seq_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            load(
                stops=[
                    stop(id="A", seq=1),
                    stop(id="B", seq=1, name="Other", pallets=[pal(id="P2")]),
                ]
            )

    def test_duplicate_pallet_id_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            load(
                stops=[
                    stop(id="A", seq=1, pallets=[pal(id="SAME")]),
                    stop(id="B", seq=2, name="B", pallets=[pal(id="SAME")]),
                ]
            )

    def test_unknown_strategy_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            load(strategy="zigzag")
