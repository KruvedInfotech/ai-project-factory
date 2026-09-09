# PickPath

Warehouse pick-path planner for a single rectangular block of picking aisles.

PickPath takes a pick wave (SKU + aisle/bay/side) and returns a walk that stays in aisle centers and the front/rear cross-aisles. It is a wave sheet, not a WMS: no inventory, no RF scans, no slotting.

## How it works

1. **Map the floor.** Aisles run front-to-back. Bay 1 is nearest the depot (front cross-aisle of aisle 1). Left/right is the pick face on that aisle. Walking never cuts through a rack: the picker uses the aisle center, then a short jog to the face.
2. **Drop illegal lines.** Aisle or bay outside the layout is skipped and listed, not routed.
3. **Build three walks, then choose.**
   - **S-shape.** Visit pick aisles left to right. Traverse a pick aisle end-to-end (enter one cross-aisle, leave the other), except the last aisle, which only goes as far as the last pick. Empty aisles are skipped. Easy for a picker to follow.
   - **Return.** Same aisle order, but every aisle is entered from the front, picked front-to-back, and exited back to the front. Use this when there is no rear cross-aisle, or when pallet jacks should not run the back.
   - **Nearest + 2-opt.** Greedy nearest remaining stop, then 2-opt on the tour. Often shorter, sometimes a zigzag that is harder to walk without a device.
4. **Auto.** Runs all three and keeps the shortest walk. Ties prefer S-shape, then return, then nearest.
5. **Time.** Walk minutes = distance / speed. Pick minutes = stops × handling seconds. Total is the sum. Quantity is for the picker, not extra stops.

### Warehouse presets

| Id | What | Aisles × bays | Pitch (m) | Rear aisle | Speed |
| --- | --- | --- | --- | --- | --- |
| `grocery_6x20` | Typical grocery / FMCG | 6×20 | 4.0 | yes | 75 m/min |
| `bulk_8x12` | Case-pick bulk | 8×12 | 5.6 | yes | 60 m/min |
| `mini_4x8` | Small demo block | 4×8 | 3.6 | yes | 75 m/min |
| `front_only_5x10` | No rear cross-aisle | 5×10 | 4.4 | no | 70 m/min |

You can override speed, handling seconds, or pass a custom layout (`aisle_count`, `bays_per_aisle`, `bay_length_m`, `aisle_width_m`, `aisle_pitch_m`, `has_rear`).

### Wave file

```json
{
  "warehouse": { "preset": "grocery_6x20" },
  "strategy": "auto",
  "picks": [
    { "sku": "MILK-1L", "aisle": 1, "bay": 3, "side": "L", "qty": 2 },
    { "sku": "TEA-500", "aisle": 5, "bay": 6, "side": "R", "qty": 6 }
  ]
}
```

`side` is `L` or `R`. SKUs need not be unique (same item, two bins).

## How to run

Needs **Python 3.10+**. No pip packages.

From this project folder (the staged copy in the factory repo is `projects/pickpath`):

```bash
# List layout presets
PYTHONPATH=src python3 -m pickpath presets

# Route an example (human-readable table + strategy comparison)
PYTHONPATH=src python3 -m pickpath route examples/grocery-wave.json

# Same result as JSON
PYTHONPATH=src python3 -m pickpath route examples/grocery-wave.json --json

# Force a strategy
PYTHONPATH=src python3 -m pickpath route examples/grocery-wave.json --strategy s_shape

# Local floor map
PYTHONPATH=src python3 -m pickpath serve --host 127.0.0.1 --port 8766
```

Then open [http://127.0.0.1:8766](http://127.0.0.1:8766).

On the page:

1. Pick a warehouse preset (default is grocery 6×20) and a strategy.
2. Edit the pick table, or load `grocery-wave`, `bulk-cluster`, `single-aisle`, or `skipped-bay`.
3. Click **Route wave**. Stops, walk metres, total time, skipped lines, and the floor map update together. The comparison line shows all three strategies.

CLI exit codes: `0` every line routed, `2` at least one line skipped, `1` usage or parse error.

### Optional install

```bash
pip install -e .
pickpath route examples/bulk-cluster.json
pickpath serve
```

### Tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Coverage includes aisle-legal walking, S-shape visit order, return routes that stay off the rear aisle, skipped locations, auto selection, CLI exit codes, and the HTTP route API.

## Examples

| File | What you should see |
| --- | --- |
| `examples/grocery-wave.json` | 13 grocery lines across 6 aisles; auto reports S-shape / return / nearest metres |
| `examples/bulk-cluster.json` | 6 case-pick lines clustered in aisles 2–3 of the bulk layout |
| `examples/single-aisle.json` | 3 SKUs in aisle 3 of the mini block; one aisle, short walk |
| `examples/skipped-bay.json` | 2 legal lines + `GHOST` in aisle 9 → exit code 2 |

## Limits

- One rectangular block. No multi-block warehouses, no mid-aisle cross-cuts.
- Greedy + 2-opt is not a guaranteed TSP optimum; S-shape and return are picker rules, not OR-optimal.
- No congestion, one-way aisles, carton volume, or batching of several orders into a wave.
- Handling time is a flat seconds-per-stop figure, not a measured pick-face standard.
