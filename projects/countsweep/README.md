# CountSweep

ABC cycle-count walk planner for warehouse pick faces and reserve slots.

CountSweep is a desk-side “what do we count today?” planner. You describe the ABC cadence, the locations, and the as-of date; it returns a walk list, leftover faces, variance flags, plus a local aisle map.

It is a planner, not a WMS. Cycle days and labor figures are typical working numbers, not a particular site configuration. It does not post adjustments and it does not freeze inventory in a live system.

## How it works

1. **Mark due.** As of the plan date, a location is due if it was never counted, or if days since the last count meet the ABC cycle (`A` / `B` / `C`). High-shrink SKUs use the shorter of the class cycle and `shrink_cycle_days`.
2. **Filter.** Blocked faces stay off the walk (`blocked`). Empty faces (`book_qty` 0) are leftover `skip-empty` when the policy skips zeros; pharma-style policies still count them.
3. **Sort the due list.** **Overdue** leads with the longest miss, then ABC. **ABC** walks A, then B, then C. **Aisle** is a serpentine walk (odd aisles low bay to high, even aisles the other way). **Shrink** puts high-shrink faces first.
4. **Walk.** Travel is `minutes_per_count + aisle_change_min × |aisle − last aisle|` (the count desk is aisle 0). When the next face would blow the labor cap, the rest of the due list is leftover `labor-cap`.
5. **Variance.** If you already keyed a `counted_qty`, CountSweep flags a miss when the absolute units or the percent miss the policy threshold. Freeze-on-count policies mark scheduled faces `freeze`. Earlier stops are never unscheduled to help a later one.

### Policy presets

| Id | What | A / B / C days | Shrink | Empty | Labor |
| --- | --- | --- | --- | --- | --- |
| `grocery_dc` | Grocery DC | 7 / 30 / 90 | 7 d | skip | 2 min + 1/aisle, 40 min |
| `pharma_vault` | Pharma vault | 1 / 7 / 30 | 1 d | count | 3 min + 1/aisle, 24 min, freeze |
| `ecom_fc` | E-com FC | 14 / 45 / 180 | 14 d | skip | 1 min + 1/aisle, 60 min |
| `bulk_reserve` | Bulk reserve | 30 / 90 / 180 | 14 d | count | 4 min + 2/aisle, 90 min |

You can override cadence, `skip_empty`, `freeze_on_count`, `minutes_per_count`, `aisle_change_min`, `max_labor_min`, `variance_pct`, or `variance_units` on a preset, or pass a custom policy with those fields. A wave may also set `labor_minutes` to cap the clock without changing the preset.

Grocery variance defaults are 5% or 2 units; the pharma vault is 2% or 1 unit.

### Wave file

```json
{
  "policy": { "preset": "grocery_dc" },
  "strategy": "overdue",
  "as_of": "2026-10-15",
  "locations": [
    {
      "id": "P-A-01-1",
      "sku": "RICE-10KG",
      "book_qty": 48,
      "abc": "A",
      "aisle": 1,
      "bay": 1,
      "level": 1,
      "last_counted": "2026-10-01",
      "high_shrink": true
    }
  ]
}
```

Each location id must be unique. ABC is `A`, `B`, or `C`. Dates are `YYYY-MM-DD`. `counted_qty` is optional (leave it off until the count is keyed). `type` is `pick` or `reserve`.

## How to run

Needs **Python 3.10+**. No pip packages.

From this project folder (the staged copy in the factory repo is `projects/countsweep`):

```bash
# List cycle-count policies
PYTHONPATH=src python3 -m countsweep presets

# Plan an example (human-readable table)
PYTHONPATH=src python3 -m countsweep plan examples/due-wave.json

# Same result as JSON
PYTHONPATH=src python3 -m countsweep plan examples/due-wave.json --json

# Local count map
PYTHONPATH=src python3 -m countsweep serve --host 127.0.0.1 --port 8775
```

Then open [http://127.0.0.1:8775](http://127.0.0.1:8775).

On the page:

1. Pick a policy (default is the grocery DC), a strategy, and the as-of date.
2. Edit the location table, or load `due-wave`, `labor-capped`, `skip-empty`, or `variance-flag`.
3. Click **Sweep counts**. The walk, leftovers, flags, and the aisle map update together.

CLI exit codes: `0` every due face scheduled, `2` at least one leftover, `1` usage or parse error.

### Optional install

```bash
pip install -e .
countsweep plan examples/due-wave.json
countsweep serve
```

### Tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Coverage includes overdue vs current faces, never-counted, high-shrink cadence, skip-empty, blocked, labor cap, ABC / aisle / shrink sort, variance flags, freeze-on-count, CLI exit codes, and the HTTP plan API.

## Examples

| File | What you should see |
| --- | --- |
| `examples/due-wave.json` | 3 due faces on a grocery DC. Never-counted SUGAR, then SOAP (14 d overdue), then high-shrink RICE. OIL, TAPE, and FLOUR stay current. Nothing left behind. |
| `examples/labor-capped.json` | Two A-class counts fill an 8-minute clock; SOAP and TAPE leftover `labor-cap` |
| `examples/skip-empty.json` | Empty A face leftover `skip-empty`; RICE is walked; OIL is still inside its 7-day cycle |
| `examples/variance-flag.json` | Pharma vault freezes both A faces. ASPIRIN is 6 units short → `flag`; SYRUP matches book; GLOVES (C) is not due yet |

## Limits

- Greedy walker: good for a fast inventory-control desk check, not a guaranteed optimal count wave.
- Cadence is calendar days, not demand-weighted or location-risk scoring beyond high-shrink.
- Blind-count UX, RF scanning, and posting book-to-physical adjustments are out of scope.
