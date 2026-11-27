# ToteHome

Empty-tote milk-run planner for pick, pack, and returns stations.

ToteHome is a dock-side “will the empties get home this hour?” planner. You describe the homes, the carts, and the piles of nested totes; it returns milk-run trips, leftover overflow, and a local floor map.

It is a planner, not a live WMS. Walk speeds and nest counts are typical dock-side figures, not a particular tote OEM spec sheet.

## How it works

1. **Totes.** Each pile is one of `std`, `cold`, or `oversize`. Empty totes nest into stacks (`python3 -m totehome totes`). A partial nest still occupies one stack slot on the cart.
2. **Urgency.** Stations at or over their pickup **threshold** are due. Stations over **cap** are overflowing. Overflow scores first, then due piles (bigger, then staler). Below-threshold piles are not seeded on their own.
3. **One type per trip.** A cart only carries one tote type, because each type drops at a different home (`std` → induction, `cold` → wash, `oversize` → buffer).
4. **Milk run.** Seed at the most urgent pile. Then nearest-neighbour along the same type, including below-threshold neighbours if the cart still has stack room and can still get home before shift end.
5. **Parallel carts.** Every cart starts at induction (else the first home). The earliest-free cart takes the next trip. A trip that cannot return before that cart’s shift ends is skipped.

Residual below the station threshold, on a station still under cap, is not a failed run.

### Floor file

```json
{
  "homes": [
    {
      "id": "IND-1",
      "kind": "induction",
      "x_m": 0,
      "y_m": 0,
      "accepts": ["std"],
      "drop_sec_per_stack": 10
    }
  ],
  "carts": [
    {
      "id": "C1",
      "stack_cap": 4,
      "speed_m_per_min": 60,
      "load_sec_per_stack": 10,
      "shift_min": 30
    }
  ],
  "stations": [
    {
      "id": "PACK-A",
      "kind": "pack",
      "x_m": 20,
      "y_m": 0,
      "threshold": 8,
      "cap": 24,
      "minutes_since_pickup": 12,
      "piles": [{ "tote": "std", "count": 12 }]
    }
  ]
}
```

Home, cart, and station ids must be unique. Coordinates are metres on the floor (Manhattan travel). `kind` for a station is `pick`, `pack`, or `returns`. Omit `accepts` on a home to use the tote types whose catalog home matches that kind.

### Tote catalog (short)

| Id | What | Nest / stack | Home |
| --- | --- | --- | --- |
| `std` | Standard nestable | 20 | induction |
| `cold` | Cold-chain / wash | 16 | wash |
| `oversize` | Awkward / non-nest | 4 | buffer |

## How to run

Needs **Python 3.10+**. No pip packages.

From this project folder (the staged copy in the factory repo is `projects/totehome`):

```bash
# List tote types and home kinds
PYTHONPATH=src python3 -m totehome totes

# Plan an example (human-readable milk runs)
PYTHONPATH=src python3 -m totehome plan examples/quiet-aisle.json

# Same result as JSON
PYTHONPATH=src python3 -m totehome plan examples/shift-short.json --json

# Local tote-return desk
PYTHONPATH=src python3 -m totehome serve --host 127.0.0.1 --port 8798
```

Then open [http://127.0.0.1:8798](http://127.0.0.1:8798).

On the page:

1. Load `quiet-aisle`, `overflow-pack`, `mixed-types`, `shift-short`, or `opportunistic`, or edit homes, carts, and stations.
2. Click **Plan runs**. Trip count, collected totes, leftover, makespan, and the floor map update together.

CLI exit codes: `0` every due/overflow pile cleared, `2` at least one leftover, `1` usage or parse error. Residual below threshold still counts as cleared.

### Optional install

```bash
pip install -e .
totehome plan examples/quiet-aisle.json
totehome serve
```

### Tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Coverage includes quiet-aisle origin, overflow-first seeding, opportunistic below-threshold pickup, mixed-type split trips, short-shift leftover, parallel carts, missing home, over-cap leftover, CLI exit codes, and the HTTP plan API.

## Examples

| File | What you should see |
| --- | --- |
| `examples/quiet-aisle.json` | PACK-A then PACK-B, **20** totes home to IND-1, makespan **2:00** (exit 0) |
| `examples/overflow-pack.json` | **PACK-HOT** first even though PACK-OK is closer, then PACK-OK (exit 0) |
| `examples/mixed-types.json` | `std` trip to IND-1, then `cold` trip to WASH-1, makespan **2:42** (exit 0) |
| `examples/shift-short.json` | NEAR collected; **FAR leftover** (too far for a 2 min shift) (exit 2) |
| `examples/opportunistic.json` | PACK-DUE seeds, **PACK-LOW** (3 totes, under threshold) rides along (exit 0) |

## Limits

- Greedy milk runs: good for a dock check, not a guaranteed optimal tour.
- One tote type per trip, no cart-to-cart transfers, no elevator / mezzanine time.
- Live tote counts, washer cycle time, and labour standards are out of scope.
