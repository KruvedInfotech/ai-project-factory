# AisleLock

Pick-aisle traffic lock for a warehouse cart wave.

AisleLock is a floor-side “will these carts collide?” planner. You describe the aisles and the carts; it stamps each walk with a start clock, lists leftovers, and draws a local aisle Gantt.

It is a planner, not a live WMS. Capacities and traverse minutes are working figures, not a particular rack OEM.

CartClip clusters tickets onto carts. PickPath routes one wave through a block. AisleLock is the step in between: several carts already have a walk, and the floor only has so many bodies in an aisle at once.

## How it works

1. **Sort the wave.** **Auto** takes hot tickets first (`priority` 1), then bulky carts, then soonest cutoff. **Cutoff** walks the clock. **Cluster** groups by first aisle. **Compact** seats the shortest walk first so more carts get a window.
2. **Claim a window.** Each cart wants the earliest start at or after `ready_min`. It walks its aisles in order. Time in an aisle is that aisle’s traverse minutes plus one minute per pick. A hop between aisles costs `minutes_per_hop`.
3. **Accept a lock** only if all of these hold:
   - Every aisle on the walk exists and matches the cart temperature (`dry` / `chill` / `freeze`, unless the aisle is `mixed`)
   - For each visit, remaining aisle capacity covers the cart (a `bulky` cart takes the whole aisle when `exclusive_bulky` is on)
   - The last visit ends on or before `cutoff_min` and the floor horizon
   - Dispatch + dwell + hops does not blow the labor cap
   - The floor still has a free cart slot (`max_carts`)
4. **Wait or leftover.** If the aisle is busy, AisleLock slides the start later. Leftovers keep a reason (`temp`, `unknown-aisle`, `cutoff`, `aisle-busy`, `labor-cap`, `cart-cap`). Earlier locks are never pulled to help a later cart.

Default labor is **5 minutes to dispatch a cart**, **aisle traverse + 1 minute per pick**, and **1 minute per hop**. A wave can override `labor_minutes`.

### Floor presets

| Id | What | Aisles | Cap | Temp | Labor | Horizon |
| --- | --- | --- | --- | --- | --- | --- |
| `grocery` | 6-aisle grocery | A–F | 2 | dry | 90 min | 120 min |
| `vna` | VNA turret (one-way) | A–D | 1 | dry | 80 min | 100 min |
| `ecom` | 8-aisle each-pick | A–H | 3 | dry | 120 min | 150 min |
| `chill` | 4-aisle chill | A–D | 1 | chill | 48 min | 80 min |

You can override labor, horizon, or `max_carts` on a preset, or pass a custom floor with an `aisles` list (`id`, `capacity`, `minutes`, `temp`).

### Wave file

```json
{
  "floor": { "preset": "grocery" },
  "strategy": "auto",
  "labor_minutes": 90,
  "exclusive_bulky": true,
  "carts": [
    {
      "id": "CART-11",
      "priority": 1,
      "temp": "dry",
      "bulky": false,
      "ready_min": 0,
      "cutoff_min": 90,
      "walk": [
        { "aisle": "A", "picks": 3 },
        { "aisle": "B", "picks": 2 }
      ]
    }
  ]
}
```

Each cart id must be unique. `priority` 1 is hottest. Temp is `dry`, `chill`, or `freeze`. Walk aisles are visited in listed order; a cart does not reverse through the same aisle.

## How to run

Needs **Python 3.10+**. No pip packages.

From this project folder (the staged copy in the factory repo is `projects/aislelock`):

```bash
# List warehouse floors
PYTHONPATH=src python3 -m aislelock presets

# Lock an example (human-readable table)
PYTHONPATH=src python3 -m aislelock lock examples/clear-wave.json

# Same result as JSON
PYTHONPATH=src python3 -m aislelock lock examples/clear-wave.json --json

# Force a strategy
PYTHONPATH=src python3 -m aislelock lock examples/narrow-busy.json --strategy cutoff

# Local aisle Gantt
PYTHONPATH=src python3 -m aislelock serve --host 127.0.0.1 --port 8783
```

Then open [http://127.0.0.1:8783](http://127.0.0.1:8783).

On the page:

1. Pick a floor (default is grocery) and a labor cap.
2. Edit the cart table, or load `clear-wave`, `narrow-busy`, `labor-capped`, or `temp-block`.
3. Click **Lock floor**. Locked count, leftovers, labor, and the aisle Gantt update together.

CLI exit codes: `0` every cart locked, `2` at least one cart left behind, `1` usage or parse error.

### Optional install

```bash
pip install -e .
aislelock lock examples/clear-wave.json
aislelock serve
```

### Tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Coverage includes overlapping wide aisles, VNA wait-or-leftover, bulky exclusive, hops, temp leftover, labor leftover, cutoff leftover, CLI exit codes, and the HTTP lock API.

## Examples

| File | What you should see |
| --- | --- |
| `examples/clear-wave.json` | 4 dry carts on grocery A–F, nothing left behind. CART-11 and CART-12 share aisle A (capacity 2) from minute 0 |
| `examples/narrow-busy.json` | VNA aisle A is one cart at a time. CART-01 takes 0–11. CART-02’s cutoff is 20, so it is leftover `aisle-busy` |
| `examples/labor-capped.json` | 12-minute cap locks `CART-31` and leaves `CART-32` as `labor-cap` |
| `examples/temp-block.json` | Chill floor locks `CART-40` and leaves dry `CART-41` as `temp` |

## Limits

- Greedy locker: good for a fast floor check, not a guaranteed optimal timetable.
- Walks are given. It does not reroute a cart around a jammed aisle.
- It does not drive RF guns, reserve labor, or talk to a WMS.
