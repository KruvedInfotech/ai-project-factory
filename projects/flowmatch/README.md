# FlowMatch

Cross-dock inbound-to-outbound matcher for a warehouse yard.

FlowMatch is a desk-side “will it flow today?” planner. You describe the inbound receipts, outbound orders, and staging lanes; it returns a match list, leftover freight, live vs staged split, plus a local flow board.

It is a planner, not a WMS or YMS. Lane sizes and clocks are typical working figures, not a particular site configuration.

## How it works

1. **Open the clock.** A receipt that arrives before yard open is available at open. Freight that arrives at or after close is leftover (`closed`).
2. **Sort the outbound queue.** Priority 1 goes first. Then the strategy decides the rest:
   - **Cutoff.** Soonest ship cutoff.
   - **Lane.** Outbound door, then cutoff — staging only, no live unload. Fill one door’s lanes before hopping.
   - **Live.** Orders that share an inbound door go first so unload-to-load can happen.
   - **Auto.** Priority then cutoff. Live when inbound and outbound doors match; otherwise stage.
3. **Consume inbound FIFO.** For each remaining outbound pallet, FlowMatch takes the earliest receipt of that SKU and temperature that can still make the cutoff.
4. **Live or stage.**
   - **Live** ready time = available + unload + load. No lane is used.
   - **Stage** ready time = available + unload + stage + load. A lane must match temperature and have remaining pallet room. Auto prefers a lane whose door equals the outbound door; lane strategy packs an already-open lane first.
5. **Accept an allocation** only if all of these hold:
   - Ready time is at or before the order cutoff and yard close
   - Adding the allocation does not exceed max matches
   - Adding the allocation does not exceed the labor cap
6. **Labor.** The first match costs `minutes_per_match`. Each later match adds the same, plus `lane_change_min` when the lane (or live door) changes. Clustering doors therefore fits more work into the same clock.
7. **Leftovers.** Outbound that is short, late, wrong temperature, out of lane room, or over the cap is listed with a reason. Inbound that nobody can take is putaway (`no-demand`, `late`, or `closed`). The process is greedy: an earlier match is never unpacked.

### Yard presets

| Id | What | Hours | Lanes | Matches | Labor |
| --- | --- | --- | --- | --- | --- |
| `fmcg_6` | FMCG cross-dock | 05:00–20:00 | 4 dry + 2 reefer | 16 | 180 min |
| `ecom_4` | Parcel / e-comm flow | 08:00–22:00 | 4 dry | 12 | 120 min |
| `cold_4` | Cold-chain | 04:00–18:00 | 4 reefer | 10 | 150 min |
| `mini_3` | Small demo dock | 08:00–16:00 | 2 dry + 1 reefer | 6 | 40 min |

You can override `open`, `close`, `live_min`, `unload_min`, `load_min`, `stage_min`, `minutes_per_match`, `lane_change_min`, `max_matches`, or `max_labor_min` on a preset, or pass a custom yard with those fields plus `lanes`.

### Flow-plan file

```json
{
  "yard": { "preset": "fmcg_6" },
  "strategy": "auto",
  "receipts": [
    { "id": "IN-MILK", "sku": "MILK-1L", "pallets": 8, "eta": "06:00", "door": "D1", "temp": "dry" }
  ],
  "orders": [
    {
      "id": "OUT-A1",
      "sku": "MILK-1L",
      "pallets": 5,
      "cutoff": "10:00",
      "door": "D1",
      "temp": "dry",
      "priority": 1
    }
  ]
}
```

Each receipt id and order id must be unique. Times are `HH:MM`. Temperature is `dry` or `reefer`.

## How to run

Needs **Python 3.10+**. No pip packages.

From this project folder (the staged copy in the factory repo is `projects/flowmatch`):

```bash
# List yard presets
PYTHONPATH=src python3 -m flowmatch presets

# Match an example (human-readable table)
PYTHONPATH=src python3 -m flowmatch match examples/grocery-same-day.json

# Same result as JSON
PYTHONPATH=src python3 -m flowmatch match examples/grocery-same-day.json --json

# Local flow board
PYTHONPATH=src python3 -m flowmatch serve --host 127.0.0.1 --port 8771
```

Then open [http://127.0.0.1:8771](http://127.0.0.1:8771).

On the page:

1. Pick a yard (default is the FMCG cross-dock) and a labor cap.
2. Edit the inbound and outbound tables, or load `grocery-same-day`, `live-unload`, `reefer-short`, or `labor-capped`.
3. Click **Match flow**. Live vs staged pallets, leftovers, and the lane board update together.

CLI exit codes: `0` everything matched, `2` at least one leftover, `1` usage or parse error.

### Optional install

```bash
pip install -e .
flowmatch match examples/live-unload.json
flowmatch serve
```

### Tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Coverage includes live vs staged doors, FIFO receipts, temperature and late leftovers, lane capacity, labor and match caps, CLI exit codes, and the HTTP match API.

## Examples

| File | What you should see |
| --- | --- |
| `examples/grocery-same-day.json` | 21 pallets through an FMCG dock, mix of live and staged, nothing left behind |
| `examples/live-unload.json` | Same-door SKU-A on the mini dock → live unload, all clear |
| `examples/reefer-short.json` | Dry inbound vs reefer outbound, plus a late reefer → `temp` and `late` leftovers |
| `examples/labor-capped.json` | Three staged matches on a 14-minute cap → at least one `capped` leftover |

## Limits

- Greedy matcher: good for a fast dock check, not a guaranteed optimal assignment.
- One SKU per receipt or order row. Split a multi-SKU order into lines with unique ids.
- No door time-slots and no pick-wave release — those are different planners.
- Factors such as seal checks, ASN variance, and pallet-label scans are out of scope.
