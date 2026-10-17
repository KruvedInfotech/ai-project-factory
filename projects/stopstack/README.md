# StopStack

Multi-stop LIFO trailer loader for milk-run deliveries.

StopStack is a dock-side “will it unload in stop order?” planner. You describe the trailer deck and the pallets per drop; it returns a nose-to-door placement list, leftover pallets, cube and weight fill, plus a local trailer map.

It is a planner, not a TMS. Deck sizes are typical inner pallet grids, not a particular OEM spec sheet. It does not print bills of lading and it does not dispatch a driver.

## How it works

1. **Open the deck.** A trailer is a grid: **row 1 is the nose**, the last row is the doors. Two columns (left / right) is the grocery default. Optional **2-high** stacking shares a floor slot when both pallets are the same stop and the stacked height still fits.
2. **Expand.** A line with `quantity: 2` becomes two physical pallets (`PAL-A-1`, `PAL-A-2`). Unique ids stay as written.
3. **Load last stop first.** Delivery `seq` 1 is the first drop, so it must sit nearest the doors. StopStack loads the highest `seq` into the nose, then walks toward the tail.
4. **Sort within a stop.** **LIFO** keeps the file order. **Heavy** / **auto** put the heaviest (then tallest) pallet first so it claims the floor. **No-mix** keeps a whole row to one stop so a driver is not walking around a foreign pallet in the same bay.
5. **Accept a slot** only if all of these hold:
   - The pallet’s temperature matches the trailer (`dry` / `reefer`), unless the trailer is `mixed`
   - The pallet is not taller than the trailer
   - Adding it does not blow the labor cap (`minutes_per_pallet` each)
   - A stack slot (same-stop floor, empty top, combined height) or the next empty floor cell from the nose is free
   - **No-mix** will not share a row with a different stop
   - Adding its weight does not exceed payload
6. **Leftovers.** Pallets that fail those checks stay on the dock with a reason (`temp`, `too-tall`, `labor-cap`, `no-slot`, `payload`). Earlier placements are never pulled to help a later pallet.

Because the nose fills first with the last delivery, each column’s stop numbers fall (or stay equal) toward the doors. First drop is at the tail; last drop is buried at the nose.

### Trailer presets

| Id | What | Grid | Stack | Inner H (mm) | Payload | Temp | Labor |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `grocery_12m` | 12 m grocery box | 11×2 | 2-high | 2400 | 18000 kg | dry | 3 min + 90 min cap |
| `city_van` | City van | 4×2 | floor | 1800 | 2500 kg | dry | 2 min + 30 min cap |
| `reefer_13m` | 13 m reefer | 12×2 | floor | 2200 | 16000 kg | reefer | 4 min + 80 min cap |
| `mini_6` | Small demo trailer | 3×2 | 2-high | 2400 | 4000 kg | mixed | 2 min + 20 min cap |

You can override `rows`, `cols`, `stack_levels`, `max_height_mm`, `max_weight_kg`, `temp`, `minutes_per_pallet`, or `max_labor_min` on a preset, or pass a custom trailer with those fields. A load may also set `labor_minutes` to cap the clock without changing the preset.

Reefer presets stay floor-only so air can move over the load. `mini_6` is mixed-temp for demos.

### Load file

```json
{
  "trailer": { "preset": "grocery_12m" },
  "strategy": "lifo",
  "stops": [
    {
      "id": "NORTH",
      "seq": 1,
      "name": "Store North",
      "pallets": [
        {
          "id": "PAL-N1",
          "sku": "MILK-1L",
          "weight_kg": 400,
          "height_mm": 1400,
          "temp": "dry",
          "quantity": 1
        }
      ]
    }
  ]
}
```

Each stop id and `seq` must be unique. Pallet ids must be unique across the load (quantity expansion suffixes `-1`, `-2`, …). `seq` 1 is the first delivery. Temp is `dry` or `reefer`. Height is millimetres; weight is kilograms.

## How to run

Needs **Python 3.10+**. No pip packages.

From this project folder (the staged copy in the factory repo is `projects/stopstack`):

```bash
# List trailer decks
PYTHONPATH=src python3 -m stopstack presets

# Stack an example (human-readable table)
PYTHONPATH=src python3 -m stopstack stack examples/milk-run.json

# Same result as JSON
PYTHONPATH=src python3 -m stopstack stack examples/milk-run.json --json

# Force a strategy
PYTHONPATH=src python3 -m stopstack stack examples/milk-run.json --strategy no-mix

# Local trailer map
PYTHONPATH=src python3 -m stopstack serve --host 127.0.0.1 --port 8776
```

Then open [http://127.0.0.1:8776](http://127.0.0.1:8776).

On the page:

1. Pick a trailer (default is the 12 m grocery box), a strategy, and a labor cap.
2. Edit the pallet table, or load `milk-run`, `payload-capped`, `labor-capped`, or `temp-mismatch`.
3. Click **Stack trailer**. Packed count, weight, leftovers, and the nose-to-door map update together.

CLI exit codes: `0` every pallet stacked, `2` at least one leftover, `1` usage or parse error.

### Optional install

```bash
pip install -e .
stopstack stack examples/milk-run.json
stopstack serve
```

### Tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Coverage includes last-stop-at-nose, first-stop-at-doors, same-stop 2-high stack, no-mix rows, payload leftover, labor cap, temp mismatch, too-tall, no-slot, heavy-within-stop order, CLI exit codes, and the HTTP stack API.

## Examples

| File | What you should see |
| --- | --- |
| `examples/milk-run.json` | 8 dry pallets on a 12 m grocery box. SOUTH (last drop) occupies nose rows 1–2, CENTRAL row 2–3, NORTH (first drop) sits at row 4 by the doors. Nothing left behind. |
| `examples/payload-capped.json` | 3× 1800 kg TILES into `mini_6` (4000 kg) → 2 packed, `PAL-H3` leftover `payload` |
| `examples/labor-capped.json` | LAST drop’s 3 pallets fill a 6-minute clock; FIRST drop leftover `labor-cap` |
| `examples/temp-mismatch.json` | Dry grocery box takes PASTA, CANS, and CRACKERS. ICE-CREAM leftover `temp` |

## Limits

- Greedy loader: good for a fast dock check, not a guaranteed optimal mix of stack vs floor.
- Support is slot-based, not a physics engine (no crushing, no load bars, no axle split).
- Live GPS, driver ETAs, and seal numbers are out of scope.
