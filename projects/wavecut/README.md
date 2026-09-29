# WaveCut

Warehouse wave release planner for outbound orders.

WaveCut is a desk-side “will it make the cutoff?” planner. You describe the shift clock and the orders; it returns timed pick waves, leftover orders, pick and cube fill, plus a local wave board.

It is a planner, not a WMS. Caps are typical working figures, not a particular site configuration.

## How it works

1. **Open the clock.** A shift is split into fixed-length wave slots from open to close. Minutes left over at the end of the day are unused.
2. **Sort the queue.** Priority 1 goes first. Then the strategy decides the rest:
   - **Cutoff.** Soonest ship cutoff, then fewest lines.
   - **Zone.** Pick zone, then cutoff — start a new wave when the zone changes if an empty slot is free.
   - **Cube.** Largest cube first so bulky orders claim early capacity.
   - **Auto.** Cutoff first, then keep an order in a wave that already has its zone when that still fits.
3. **Accept a wave** only if all of these hold:
   - The wave start plus the order’s pick minutes is still at or before the cutoff
   - Adding the order does not exceed max orders, lines, cube, or pick minutes
   - On a **zone-pure** shift, the wave is empty or already that zone
4. **Leftovers.** Orders that are over any hard cap, or that cannot finish picking before cutoff, are listed with a reason. The process is greedy: an earlier assignment is never unpacked to make a later one fit.

### Shift presets

| Id | What | Hours | Wave | Caps | Zone-pure |
| --- | --- | --- | --- | --- | --- |
| `grocery_am` | Store replenishment | 05:00–12:00 | 30 min | 3 orders / 28 lines / 2.0 m³ / 70 pick-min | no |
| `ecom_day` | Same-day e-comm | 08:00–20:00 | 45 min | 4 orders / 20 lines / 1.2 m³ / 50 pick-min | no |
| `wholesale_pm` | Wholesale dispatch | 12:00–22:00 | 60 min | 8 orders / 120 lines / 16 m³ / 240 pick-min | yes |
| `mini_3` | Small demo shift | 08:00–12:00 | 60 min | 3 orders / 20 lines / 2.0 m³ / 60 pick-min | no |

You can override `open`, `close`, `wave_min`, the caps, or `zone_pure` on a preset, or pass a custom shift with those fields.

### Wave-plan file

```json
{
  "shift": { "preset": "grocery_am" },
  "strategy": "auto",
  "orders": [
    {
      "id": "SO-1042",
      "channel": "store",
      "zone": "ambient",
      "lines": 6,
      "units": 48,
      "cube_m3": 0.42,
      "pick_min": 18,
      "cutoff": "08:30",
      "priority": 1
    }
  ]
}
```

Each order id must be unique. Times are `HH:MM` on a single working day (`24:00` is allowed as shift close). Channel is `store`, `ecom`, `wholesale`, or `other`. Zone is `ambient`, `chill`, `freezer`, or `bulk`. Priority `1` is first in line.

## How to run

Needs **Python 3.10+**. No pip packages.

From this project folder (the staged copy in the factory repo is `projects/wavecut`):

```bash
# List shift presets
PYTHONPATH=src python3 -m wavecut presets

# Cut an example (human-readable board)
PYTHONPATH=src python3 -m wavecut cut examples/morning-stores.json

# Same result as JSON
PYTHONPATH=src python3 -m wavecut cut examples/morning-stores.json --json

# Force a strategy
PYTHONPATH=src python3 -m wavecut cut examples/morning-stores.json --strategy zone

# Local wave board
PYTHONPATH=src python3 -m wavecut serve --host 127.0.0.1 --port 8768
```

Then open [http://127.0.0.1:8768](http://127.0.0.1:8768).

On the page:

1. Pick a shift (default is grocery AM) and a strategy.
2. Edit the order table, or load `morning-stores`, `ecom-cutoff`, `zone-batch`, or `missed-cutoff`.
3. Click **Cut waves**. Assigned count, pick fill, leftovers, and the wave Gantt update together.

CLI exit codes: `0` every order assigned, `2` at least one leftover, `1` usage or parse error.

### Optional install

```bash
pip install -e .
wavecut cut examples/zone-batch.json
wavecut serve
```

### Tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Coverage includes first-wave placement, cutoff leftovers, cube/line caps, spill into the next slot, zone-pure separation, auto zone affinity, cube-first ordering, CLI exit codes, and the HTTP cut API.

## Examples

| File | What you should see |
| --- | --- |
| `examples/morning-stores.json` | 8 store orders into the grocery AM shift; nothing left behind, at least two waves used |
| `examples/ecom-cutoff.json` | 8 same-day e-comm orders, cutoff-first, all assigned |
| `examples/zone-batch.json` | Wholesale PM: ambient and chill stay on separate zone-pure waves |
| `examples/missed-cutoff.json` | `KEEP-A` / `KEEP-B` assign; `LATE` misses 08:10; `HUGE` is over cube |

## Limits

- One working day. No multi-day carry, no live labour punch-in.
- Greedy assignment: good for a fast desk check, not a guaranteed optimal mix.
- Pick minutes are a flat estimate, not a travel-path or aisle-walk model.
- Carton cube inside a truck and dock-door booking are out of scope.
