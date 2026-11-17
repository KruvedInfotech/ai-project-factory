# ShipCut

Outbound carrier cutoff clock for one packed order.

ShipCut is a dock-side “will it still make today’s pickup, and still make the promise?” desk. You describe when the order will be ready, the promised date, the destination zone, and the pieces; it returns the next pickup per carrier, who still makes the SLA, and how many minutes are left on the soonest open cutoff.

It is a planner, not a live carrier feed. Cutoffs and transit are typical screening figures, not a contract or a booking.

## How it works

1. **Zone.** Use `zone` (`Z1`–`Z5`) or `distance_km`. Road kilometres map to metro / near / regional / long / national bands (80 / 250 / 500 / 1,000 km).
2. **Expand.** A SKU with `quantity: 4` becomes four physical pieces. Any piece over a carrier’s kg or longest-side cap is a no-go for that carrier.
3. **Next pickup.** If ready-to-ship is on a pickup day and at or before cutoff, pickup is that cutoff. Otherwise ShipCut walks forward day by day (two weeks) until the next pickup weekday.
4. **Transit.** Delivery is pickup date plus the carrier’s calendar days for that zone. Sunday always rolls to Monday. Carriers that skip Saturday delivery roll Saturday to Monday too. Transit `0` is same-calendar-day (metro same-day).
5. **Status.**
   - **makes_sla** — next pickup delivers on or before the promise
   - **missed_cutoff** — today’s cutoff would have made the promise, but ready-to-ship is already past it, and the next pickup is late
   - **late** — even the next pickup misses the promise
   - **oversize** / **zone_blocked** — piece cap or the carrier does not serve that zone
6. **Winner.** Among carriers that make the SLA, earliest delivery wins, then earliest pickup (gets on a truck sooner).

### Zones

| Id | What | Road km |
| --- | --- | --- |
| `Z1` | Metro | ≤ 80 |
| `Z2` | Near | ≤ 250 |
| `Z3` | Regional | ≤ 500 |
| `Z4` | Long | ≤ 1,000 |
| `Z5` | National | above |

### Screening carriers

| Id | What | Cutoff | Pickup | Transit (days) | Caps |
| --- | --- | --- | --- | --- | --- |
| `metro_same` | Metro same-day | 12:00 | Mon–Sat | Z1:0 Z2:1 | 20 kg / 80 cm |
| `air_express` | Air express | 15:00 | Mon–Sat | 1 / 1 / 2 / 2 / 3 | 30 kg / 120 cm |
| `night_run` | Night linehaul | 21:00 | Mon–Sat | 1 / 1 / 2 / 3 / 4 | 40 kg / 120 cm |
| `ground_std` | Ground standard | 18:00 | Mon–Sat | 1 / 2 / 3 / 4 / 5 | 50 kg / 150 cm |
| `economy` | Economy road | 17:00 | Mon–Fri | 2 / 3 / 4 / 5 / 7 | 70 kg / 180 cm |

Transit cells for air/night/ground/economy are Z1 through Z5. Metro same-day does not serve Z3–Z5. Night linehaul, ground, metro, and economy skip Saturday delivery.

### Order file

```json
{
  "origin": "Ahmedabad DC",
  "destination": "Satellite",
  "ready_at": "2026-11-17T10:30:00",
  "promised_on": "2026-11-17",
  "zone": "Z1",
  "pieces": [
    {
      "sku": "KIT-A",
      "length_cm": 30,
      "width_cm": 20,
      "height_cm": 12,
      "weight_kg": 1.4,
      "quantity": 2
    }
  ]
}
```

Each SKU must be unique. Dimensions are centimetres. You can omit `zone` and pass `distance_km` instead. Datetimes are naive local warehouse time.

## How to run

Needs **Python 3.10+**. No pip packages.

From this project folder (the staged copy in the factory repo is `projects/shipcut`):

```bash
# List screening carriers and zones
PYTHONPATH=src python3 -m shipcut cards

# Check an example (human-readable board)
PYTHONPATH=src python3 -m shipcut check examples/same-day.json

# Same result as JSON
PYTHONPATH=src python3 -m shipcut check examples/missed-cutoff.json --json

# Local cutoff clock
PYTHONPATH=src python3 -m shipcut serve --host 127.0.0.1 --port 8793
```

Then open [http://127.0.0.1:8793](http://127.0.0.1:8793).

On the page:

1. Load `same-day`, `missed-cutoff`, `weekend-roll`, or `too-late`, or edit the piece table.
2. Set ready-to-ship, promised date, and zone (or road km).
3. Click **Check cutoffs**. Winner, minutes left, the today timeline, and five carrier rows update together.

CLI exit codes: `0` at least one carrier makes the promise, `2` none do, `1` usage or parse error.

### Optional install

```bash
pip install -e .
shipcut check examples/weekend-roll.json
shipcut serve
```

### Tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Coverage includes same-day metro win, missed air cutoff vs night linehaul, Friday-to-Monday weekend roll, oversize caps, zone mapping, CLI exit codes, and the HTTP check API.

## Examples

| File | What you should see |
| --- | --- |
| `examples/same-day.json` | Tuesday 10:30, metro promise today → **metro same-day** (90 min left); air is next-day, late |
| `examples/missed-cutoff.json` | Tuesday 17:10, Z2 promised Wednesday → air/metro **missed cutoff**; **night linehaul** still open until 21:00 |
| `examples/weekend-roll.json` | Friday 19:30, 620 km (Z4) promised Monday → **night linehaul** tonight; air still makes it on Saturday pickup |
| `examples/too-late.json` | Friday 22:00, Z5 promised Saturday → no carrier makes it (exit 2) |

## Limits

- Screening cards, not a live carrier portal: cutoffs, transit, and caps vary by account and lane.
- Transit is calendar days plus a weekend roll, not a full holiday calendar or SLA clock that pauses on Sundays only.
- One origin, one destination, one ready time. Multi-piece split across carriers, appointments, and dim-weight rating are out of scope (use [LoadFit](../loadfit/) for cube).
- Naive local time only — no time zones, DST, or UTC offsets.
