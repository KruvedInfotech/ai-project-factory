# ReturnSort

Returns-dock disposition and putback planner.

ReturnSort is a dock-side “where does this unit go?” planner. You describe the returns floor and the inbound tickets; it grades each piece, parks it in a lane, lists leftovers, and draws a local floor map.

It is a planner, not a live WMS. Lane sizes are working slot counts, not a particular location master.

## How it works

1. **Expand.** A ticket with `quantity: 3` becomes three physical units.
2. **Grade.** Disposition is derived from reason + grade:
   - vendor / `rma` → **rma**
   - suspect / quality / recall / hold → **hold**
   - damaged / crushed / wet → **scrap**
   - repairable, or opened/defective/missing-parts → **refurb** (opened + sellable goes back to **restock**)
   - sellable unwanted / wrong-item / fit → **restock**
3. **Sort.** Hold and RMA leave the apron first, then perishable remaining life, then A-velocity restock, then refurb, then scrap.
4. **Pick a lane** only if all of these hold:
   - The lane accepts that disposition
   - Temperature matches (dry / chill / freeze)
   - A slot is still open
   - Adding its minutes does not exceed the labor cap
5. **Prefer.** Same SKU already in the lane, then the preferred zone (A/B restock → pick face, C → reserve), then door-adjacent lanes for RMA, then the emptiest legal lane.
6. **Leftovers.** Pieces that fail those checks are listed as unparked. The process is greedy: it will not move an earlier unit to make a later one fit.

Default labor is 2 minutes restock, 6 refurb, 1 scrap, 3 RMA, 2 hold. A ticket can override `minutes`.

### Floor presets

| Id | What | Lanes |
| --- | --- | --- |
| `dc_returns` | Typical DC returns room | pick-face A/B, chill restock, reserve, refurb, scrap, RMA dock, quality hold |
| `3pl_mixed` | 3PL multi-client room | two client faces, chill, freeze, shared reserve, refurb, scrap, RMA, hold |
| `store_backroom` | Small store backroom | floor restock, cooler, repair table, damage bin, manager hold |

You can pass a custom floor with `lanes` (`id`, `dispositions`, `temp`, `slots`, `zone`, optional `door_adjacent`, `col`, `row`).

### Batch file

```json
{
  "floor": { "preset": "dc_returns" },
  "labor_minutes": 90,
  "units": [
    {
      "ticket": "R-1001",
      "sku": "TEE-BLK-M",
      "reason": "unwanted",
      "grade": "sellable",
      "temp": "dry",
      "velocity": "A",
      "quantity": 3
    }
  ]
}
```

Each ticket must be unique. `temp` is `dry`, `chill`, or `freeze`. `velocity` is `A`, `B`, or `C`. Optional `remaining_life_days` pulls perishable restock forward.

## How to run

Needs **Python 3.10+**. No pip packages.

From this project folder (the staged copy in the factory repo is `projects/returnsort`):

```bash
# List floor presets
PYTHONPATH=src python3 -m returnsort floors

# Plan an example (human-readable table)
PYTHONPATH=src python3 -m returnsort plan examples/mixed-returns.json

# Same result as JSON
PYTHONPATH=src python3 -m returnsort plan examples/mixed-returns.json --json

# Local returns map
PYTHONPATH=src python3 -m returnsort serve --host 127.0.0.1 --port 8765
```

Then open [http://127.0.0.1:8765](http://127.0.0.1:8765).

On the page:

1. Pick a floor (default is the DC returns room) and a labor cap.
2. Edit the ticket table, or load `mixed-returns`, `quality-holds`, or `labor-capped`.
3. Click **Plan dock**. Parked count, labor, disposition mix, leftovers, and the floor map update together.

CLI exit codes: `0` everything parked, `2` at least one unit left behind, `1` usage or parse error.

### Optional install

```bash
pip install -e .
returnsort plan examples/quality-holds.json
returnsort serve
```

### Tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Coverage includes disposition grading, pick-face vs reserve, same-SKU affinity, chill match, labor leftovers, freeze leftover, CLI exit codes, and the HTTP plan API.

## Examples

| File | What you should see |
| --- | --- |
| `examples/mixed-returns.json` | 16 units into the DC room, nothing left behind |
| `examples/quality-holds.json` | Recall/quality to HOLD, chill hold to CHILL-1, vendor to RMA |
| `examples/labor-capped.json` | 12 minutes in a backroom → some refurb waits; freeze has no lane |

## Limits

- Greedy planner: good for a fast dock check, not a guaranteed optimal putback.
- Disposition is rule-based (reason + grade), not a full claims or grading workstation.
- Factors such as serial capture, photo evidence, and refund posting are out of scope.
