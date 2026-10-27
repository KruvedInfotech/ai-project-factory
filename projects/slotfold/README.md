# SlotFold

Honeycomb location consolidator for a warehouse rack room.

SlotFold is a floor-side “can we free this slot?” planner. You describe occupied locations; it folds partials of the same SKU together, lists leftovers, and draws a local rack map.

It is a planner, not a live WMS. Aisle counts are working figures, not a particular location master.

## How it works

1. **Group.** Locations that share SKU + lot + temperature form a fold family. Empty, locked, and quality-hold locations do not donate or receive.
2. **Split roles.** Within a family, **sinks** keep inventory (fuller locations, especially pick faces). **Donors** try to empty (reserve first, then the emptiest).
3. **Protect pick faces.** With `keep_last_pick_face` on (the default), the last pick-face of a SKU will not donate.
4. **Move** a donor into the best sink only if all of these hold:
   - The sink already holds that SKU / lot / temp
   - Units fit remaining quantity and weight
   - Adding the trip does not exceed the labor cap
5. **Prefer.** Same aisle, then nearest bay, then the fullest sink (top-off).
6. **Freed / leftovers.** A donor that hits quantity 0 is a freed slot. Pieces that fail the checks stay on the leftover board with a reason. The process is greedy: it will not unpack an earlier move to make a later one fit.

Default labor is **4 minutes per donor→sink trip**. A plan can override `minutes_per_move`.

### Warehouse presets

| Id | What | Aisles × bays × levels |
| --- | --- | --- |
| `small_dc` | 4-aisle case pick | 4 × 10 × 3 |
| `grocery` | 6-aisle grocery | 6 × 12 × 4 |
| `ecom` | 8-aisle each-pick | 8 × 16 × 3 |

You can pass a custom room with `aisles`, `bays`, and `levels`.

### Plan file

```json
{
  "warehouse": { "preset": "small_dc" },
  "labor_minutes": 48,
  "keep_last_pick_face": true,
  "locations": [
    {
      "aisle": "A",
      "bay": 1,
      "level": 1,
      "sku": "TEE-BLK-M",
      "qty": 5,
      "max_qty": 20,
      "kind": "reserve",
      "temp": "dry"
    }
  ]
}
```

Each location must be unique on aisle / bay / level. `kind` is `pick` or `reserve`. `temp` is `dry`, `chill`, or `freeze`. Optional `lot`, `unit_kg`, `max_kg`, `locked`, and `hold`.

## How to run

Needs **Python 3.10+**. No pip packages.

From this project folder (the staged copy in the factory repo is `projects/slotfold`):

```bash
# List warehouse presets
PYTHONPATH=src python3 -m slotfold presets

# Fold an example (human-readable table)
PYTHONPATH=src python3 -m slotfold fold examples/mixed-partials.json

# Same result as JSON
PYTHONPATH=src python3 -m slotfold fold examples/mixed-partials.json --json

# Local rack map
PYTHONPATH=src python3 -m slotfold serve --host 127.0.0.1 --port 8779
```

Then open [http://127.0.0.1:8779](http://127.0.0.1:8779).

On the page:

1. Pick a rack room (default is the 4-aisle case pick) and a labor cap.
2. Edit the location table, or load `same-aisle`, `mixed-partials`, or `labor-capped`.
3. Click **Fold slots**. Moves, freed slots, leftovers, and the rack map update together.

CLI exit codes: `0` every donor emptied, `2` at least one location left behind, `1` usage or parse error.

### Optional install

```bash
pip install -e .
slotfold fold examples/same-aisle.json
slotfold serve
```

### Tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Coverage includes same-aisle top-off, pick-face protection, lock/hold skips, temperature families, weight leftover, labor leftovers, CLI exit codes, and the HTTP fold API.

## Examples

| File | What you should see |
| --- | --- |
| `examples/same-aisle.json` | 6 WATER from B-02-1 into B-07-1, pick face stays, one slot freed |
| `examples/mixed-partials.json` | 4 SKUs fold cleanly in the small DC, four slots freed |
| `examples/labor-capped.json` | 8 minutes → two trips; locked SOAP and held MILK stay on the board |

## Limits

- Greedy consolidator: good for a fast honeycomb check, not a guaranteed minimum-travel wave.
- Sinks must already hold the SKU. SlotFold will not open an empty location.
- Factors such as equipment type, pallet jack travel time, and live inventory locks are out of scope.
