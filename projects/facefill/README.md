# FaceFill

Pick-face replenishment planner for a warehouse forward-pick area.

FaceFill is a desk-side “will the face survive the wave?” planner. You describe the pick faces, reserve pallets, and upcoming demand; it returns a drop list, leftover faces, fill after the drop, plus a local aisle heat map.

It is a planner, not a WMS. Min/max levels and travel minutes are typical working figures, not a particular site configuration.

## How it works

1. **Read the faces.** Each pick face has a SKU, aisle, bay, min, max, on-hand units, and units per case. One face per SKU.
2. **Apply demand.** Upcoming wave units for that SKU are subtracted from on-hand. A face already below min, or that will drop below min after the wave, needs a drop.
3. **Size the drop.** When a face is triggered, FaceFill fills toward **max**. Cases = floor((max − on-hand) / case qty). The face never goes over max. If a single case does not fit in the remaining room, the face is leftover.
4. **Pull reserve.** Reserve pallets for that SKU are consumed **nearest aisle first** (then location id). Several pallets may feed one face. Partial pallets are allowed.
5. **Accept a task** only if all of these hold:
   - The face is on the layout
   - At least one case is available in reserve
   - Adding the task does not exceed max tasks
   - Adding the task does not exceed the labor cap
6. **Labor.** The first drop costs `minutes_per_task + aisle_change_min × aisle` (depot is aisle 0). Each later drop adds `minutes_per_task + aisle_change_min × |aisle − previous aisle|`. Clustering aisles therefore fits more work into the same clock.
7. **Leftovers.** Faces that are outside the layout, have no reserve, cannot take a case, exceed the caps, or are still below min after a short pallet are listed with a reason. The process is greedy: an earlier drop is never unpacked.

### Strategies

- **Urgent.** Faces already below min first, then lowest fill %.
- **Demand.** Largest upcoming wave demand first.
- **Cluster.** Aisle then bay — a reach-truck loop that stays in one aisle.
- **Auto.** Faces already below min first, then aisle cluster.

### Warehouse presets

| Id | What | Aisles × bays | Tasks | Labor | Minutes |
| --- | --- | --- | --- | --- | --- |
| `grocery_6` | Grocery forward pick | 6×8 | 12 | 90 min | 6 + 4/aisle |
| `ecom_4` | E-comm piece pick | 4×10 | 10 | 60 min | 5 + 3/aisle |
| `wholesale_8` | Wholesale case pick | 8×6 | 16 | 120 min | 8 + 5/aisle |
| `mini_3` | Small demo block | 3×4 | 6 | 40 min | 5 + 4/aisle |

You can override `max_tasks`, `max_labor_min`, `minutes_per_task`, or `aisle_change_min` on a preset, or pass a custom warehouse with those fields plus `aisle_count` and `bays_per_aisle`.

### Replen-plan file

```json
{
  "warehouse": { "preset": "grocery_6" },
  "strategy": "auto",
  "faces": [
    {
      "id": "A1-03",
      "sku": "MILK-1L",
      "aisle": 1,
      "bay": 3,
      "min_qty": 24,
      "max_qty": 96,
      "on_hand": 12,
      "case_qty": 12,
      "priority": 1
    }
  ],
  "reserve": [
    { "id": "R-12", "sku": "MILK-1L", "aisle": 12, "cases": 8 }
  ],
  "demand": [
    { "sku": "MILK-1L", "units": 36 }
  ]
}
```

Each face id and SKU must be unique. Demand lines with the same SKU are summed. Priority `1` is first in line on the urgent and demand sorts.

## How to run

Needs **Python 3.10+**. No pip packages.

From this project folder (the staged copy in the factory repo is `projects/facefill`):

```bash
# List warehouse presets
PYTHONPATH=src python3 -m facefill presets

# Plan an example (human-readable drop list)
PYTHONPATH=src python3 -m facefill fill examples/morning-grocery.json

# Same result as JSON
PYTHONPATH=src python3 -m facefill fill examples/morning-grocery.json --json

# Force a strategy
PYTHONPATH=src python3 -m facefill fill examples/labor-capped.json --strategy urgent

# Local face board
PYTHONPATH=src python3 -m facefill serve --host 127.0.0.1 --port 8769
```

Then open [http://127.0.0.1:8769](http://127.0.0.1:8769).

On the page:

1. Pick a warehouse (default is grocery forward pick) and a labor cap.
2. Edit the face table, or load `morning-grocery`, `reserve-short`, `labor-capped`, or `wave-breach`.
3. Click **Fill faces**. Task count, cases, labor, leftovers, and the aisle heat map update together.

CLI exit codes: `0` every triggered face is healthy after the plan, `2` at least one leftover, `1` usage or parse error.

### Optional install

```bash
pip install -e .
facefill fill examples/morning-grocery.json
facefill serve
```

### Tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Coverage includes fill-to-max, wave-breach trigger, nearest reserve, short pallets, labor vs cluster, task cap, demand order, CLI exit codes, and the HTTP fill API.

## Examples

| File | What you should see |
| --- | --- |
| `examples/morning-grocery.json` | 5 drops into a grocery block, every face healthy after |
| `examples/reserve-short.json` | OK filled; SHORT partial; NONE no pallet; BLOCK cannot take a case |
| `examples/labor-capped.json` | Cluster keeps 3 aisle-1 drops; aisle 2 and 3 miss the 22-minute cap |
| `examples/wave-breach.json` | Faces still above min until demand; PEN pulls the nearest reserve first |

## Limits

- Greedy planner: good for a fast desk check, not a guaranteed optimal labor tour.
- Demand is by SKU, and each SKU has one face. Split-location SKUs are out of scope.
- Reserve is cases only — no lot, FEFO, or let-down equipment constraints.
- Travel is aisle-change minutes, not a full warehouse walk (see PickPath for that).
