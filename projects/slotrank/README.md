# SlotRank

Velocity-based slotting planner for a warehouse forward-pick area.

SlotRank is a desk-side “are the fast movers in the golden zone?” planner. You describe the pick faces and SKU demand; it classifies ABC, proposes new homes, and returns a move list plus a local slot map.

It is a planner, not a WMS. Golden-zone boxes and travel minutes are typical working figures, not a particular site configuration.

## How it works

1. **Read the SKUs.** Each line has picks in the lookback, cube, weight, pick type (`piece` / `case` / `pallet`), an optional family, and the current face id. One row per SKU.
2. **Classify ABC.** SKUs are sorted by picks. Walking down that list, a SKU stays **A** until cumulative picks reach 80% of the warehouse, **B** until 95%, and **C** after that. Zero-pick catalogs are all C.
3. **Score faces.** A face is legal only when the pick type matches, cube fits, and a heavy SKU sits on a floor bay (bay 1 on the presets). Score is depot distance (`aisle + 0.2 × bay`) plus a class-fit penalty: A wants the golden zone, C wants to leave it, B is almost indifferent.
4. **Assign.** Highest-priority SKUs claim the best remaining face. If the current home is still free and within 1.0 of the best score, SlotRank **keeps** it to avoid churn.
5. **Strategies** change the claim order and the score:
   - **Velocity.** A, then B, then C. Highest picks first.
   - **Affinity.** Same order, but a family prefers the aisle where a partner already landed.
   - **Heavy.** Heavy SKUs first, onto floor bays, then velocity for the rest.
   - **Auto.** Heavy first, then velocity with affinity.
6. **Moves.** A SKU that changes face becomes a move. Labor is `minutes_per_move + aisle_change_min × |from − to aisle|` (unslotted SKUs start at aisle 0). Moves are taken highest benefit first until the move or labor cap. The rest are **later** leftovers. Faces that have no legal home are leftovers with `no-slot` or `no-heavy-slot`.

The process is greedy: an earlier assignment is never unpacked.

### Warehouse presets

| Id | What | Aisles × bays | Golden zone | Moves | Labor |
| --- | --- | --- | --- | --- | --- |
| `grocery_6` | Grocery forward pick | 6×8 | A1–A2, bays 1–4 | 12 | 90 min |
| `ecom_4` | E-comm piece pick | 4×10 | A1–A2, bays 1–5 | 10 | 60 min |
| `wholesale_8` | Wholesale case pick | 8×6 | A1–A3, bays 1–3 | 16 | 120 min |
| `mini_3` | Small demo block | 3×4 | A1, bays 1–2 | 6 | 40 min |

Bay 1 of every aisle is the floor bay (`allow_heavy`). You can override `max_moves`, `max_labor_min`, `minutes_per_move`, or `aisle_change_min` on a preset, or pass a custom warehouse plus an explicit `locations` list.

### Slot-plan file

```json
{
  "warehouse": { "preset": "grocery_6" },
  "strategy": "auto",
  "skus": [
    {
      "sku": "MILK-1L",
      "picks": 420,
      "cube": 18,
      "weight_kg": 12,
      "slot_type": "case",
      "family": "dairy",
      "current": "A5-07"
    }
  ]
}
```

Each SKU must be unique. `cube` is a working volume unit (enough that `max_cube` can reject an oversized face). Omit `locations` to use the generated aisle × bay grid. `heavy` is optional; if omitted, weight ≥ 15 kg counts as heavy. Priority of the ABC cut can be overridden with `a_share` / `b_share` on the warehouse.

## How to run

Needs **Python 3.10+**. No pip packages.

From this project folder (the staged copy in the factory repo is `projects/slotrank`):

```bash
# List warehouse presets
PYTHONPATH=src python3 -m slotrank presets

# Rank an example (human-readable table)
PYTHONPATH=src python3 -m slotrank slot examples/mis-slotted-grocery.json

# Same result as JSON
PYTHONPATH=src python3 -m slotrank slot examples/mis-slotted-grocery.json --json

# Local slot board
PYTHONPATH=src python3 -m slotrank serve --host 127.0.0.1 --port 8770
```

Then open [http://127.0.0.1:8770](http://127.0.0.1:8770).

On the page:

1. Pick a warehouse (default is grocery) and a labor cap.
2. Edit the SKU table, or load `mis-slotted-grocery`, `affinity-ecom`, `labor-capped`, or `heavy-floor`.
3. Click **Rank slots**. A-in-golden, travel, this-wave moves, leftovers, and the aisle map update together.

CLI exit codes: `0` every SKU has a home and every needed move fits the wave, `2` at least one leftover, `1` usage or parse error.

### Optional install

```bash
pip install -e .
slotrank slot examples/affinity-ecom.json
slotrank serve
```

### Tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Coverage includes ABC bands, golden-zone preference, keep-if-close, type/cube/heavy leftovers, affinity clustering, heavy-first order, labor and move caps, CLI exit codes, and the HTTP slot API.

## Examples

| File | What you should see |
| --- | --- |
| `examples/mis-slotted-grocery.json` | Fast grocery SKUs in the back aisles, C items sitting in the golden zone → A faces move forward |
| `examples/affinity-ecom.json` | Tea and snack families scattered; affinity keeps each family on one aisle |
| `examples/labor-capped.json` | Several A SKUs want aisle 1; 14 minutes covers the top move plus a cheap C slide, and leaves the rest for later |
| `examples/heavy-floor.json` | Oil, rice, and water come off high bays onto bay-1 floor faces |

## Limits

- Greedy slotter: good for a weekend move wave, not a guaranteed optimal assignment.
- One SKU per face. No multi-face SKUs, no pick-clean / pick-to-zero rules.
- Golden zone is a rectangle of aisles and bays, not a full 3D waist-height model.
- Affinity is “same aisle as the first family member placed,” not a full market-basket solver.
