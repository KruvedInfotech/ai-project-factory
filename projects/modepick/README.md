# ModePick

Parcel vs LTL vs FTL picker for one outbound shipment.

ModePick is a dock-side “which mode is cheapest, and what is a no-go?” desk. You describe the pieces and the road kilometres; it returns three quotes, a winner, and the reason a mode cannot take the load.

It is a planner, not a carrier tariff. Rate cards are typical screening figures, not a contract or a booking.

## How it works

1. **Weigh the shipment.** Each SKU with `quantity: 8` becomes eight physical pieces. ModePick totals actual kilograms, cube, longest edge, and density.
2. **Parcel.** Each piece is billed at `max(actual kg, L×W×H cm³ / 5000)`, rounded up to the next 0.5 kg. A zone from road km sets $/kg and a per-piece minimum, then 12% fuel. A piece is a no-go if billable weight is over 30 kg, any side is over 120 cm, or length + girth is over 300 cm (girth uses the two shorter sides).
3. **LTL.** Density as lb/ft³ maps to a simplified NMFC-style class. Chargeable hundredweight is `max(actual lb, 150) / 100`. The class-100 CWT rate for the km band is scaled by `class / 100`, discounted 45%, then 18% fuel. A $95 minimum applies. Shipments over **4,500 kg** or **8 m³** are a no-go (those belong on a truck).
4. **FTL.** The smallest truck that holds the cube at **85%** of inner volume and the payload wins that mode. Cost is `max(minimum, $/km × km)`. Cube screening is not a 3D pack — use [LoadFit](../loadfit/) if you need overlap-free placement.
5. **Winner.** Among feasible modes, the lowest dollar total wins. Savings is versus the next feasible quote.

### Parcel zones

| Zone | Road km | $/kg | Min / piece |
| --- | --- | --- | --- |
| Z1 | ≤ 80 | 4.20 | 8.50 |
| Z2 | ≤ 250 | 5.10 | 9.50 |
| Z3 | ≤ 500 | 6.40 | 11.00 |
| Z4 | ≤ 1,000 | 8.20 | 13.00 |
| Z5 | ≤ 1,800 | 10.50 | 16.00 |
| Z6 | above | 13.80 | 19.00 |

### LTL class from density

| lb/ft³ | Class |
| --- | --- |
| ≥ 30 | 70 |
| ≥ 22.5 | 85 |
| ≥ 15 | 92.5 |
| ≥ 12 | 100 |
| ≥ 10.5 | 125 |
| ≥ 8 | 150 |
| ≥ 6 | 175 |
| ≥ 4 | 250 |
| else | 300 |

Class-100 CWT: $28 / $42 / $58 / $78 / $105 / $132 on the same km bands as the parcel zones.

### FTL trucks

| Id | What | Inner cube (m³) | Payload (kg) | $/km | Min |
| --- | --- | --- | --- | --- | --- |
| `van_407` | Light truck / 407-class | 8.88 | 2500 | 1.15 | 90 |
| `truck_14ft` | 14 ft box truck | 19.37 | 4000 | 1.55 | 140 |
| `truck_20ft` | 20 ft box truck | 29.62 | 7000 | 1.95 | 220 |
| `trailer_32ft` | 32 ft trailer | 56.45 | 12000 | 2.40 | 320 |

Usable cube is 85% of inner volume.

### Shipment file

```json
{
  "origin": "Ahmedabad DC",
  "destination": "Pune hub",
  "distance_km": 620,
  "pieces": [
    {
      "sku": "A-CARTON",
      "length_cm": 60,
      "width_cm": 40,
      "height_cm": 40,
      "weight_kg": 50,
      "quantity": 8
    }
  ]
}
```

Each SKU must be unique. Dimensions are centimetres. You can omit `distance_km` and pass `origin` / `destination` as `{ "name", "lat", "lon" }` — ModePick then uses great-circle kilometres (not road km).

Optional overrides: `fuel_parcel`, `fuel_ltl`, `ltl_discount`, `dim_divisor`.

## How to run

Needs **Python 3.10+**. No pip packages.

From this project folder (the staged copy in the factory repo is `projects/modepick`):

```bash
# List screening cards
PYTHONPATH=src python3 -m modepick cards

# Quote an example (human-readable table)
PYTHONPATH=src python3 -m modepick quote examples/small-parcel.json

# Same result as JSON
PYTHONPATH=src python3 -m modepick quote examples/mid-ltl.json --json

# Local rate desk
PYTHONPATH=src python3 -m modepick serve --host 127.0.0.1 --port 8792
```

Then open [http://127.0.0.1:8792](http://127.0.0.1:8792).

On the page:

1. Load `small-parcel`, `mid-ltl`, or `full-truck`, or edit the piece table.
2. Set origin, destination, and road kilometres.
3. Click **Quote modes**. Winner, savings, class, and the three cards update together.

CLI exit codes: `0` at least one feasible mode, `2` nothing fits, `1` usage or parse error.

### Optional install

```bash
pip install -e .
modepick quote examples/full-truck.json
modepick serve
```

### Tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Coverage includes DIM vs actual weight, parcel size caps, LTL class and minimum charge, FTL truck step-up, example winners, lat/lon distance, CLI exit codes, and the HTTP quote API.

## Examples

| File | What you should see |
| --- | --- |
| `examples/small-parcel.json` | 4 light kits, 32 km → **parcel** wins (LTL hits the $95 minimum) |
| `examples/mid-ltl.json` | 8× 50 kg cartons, 620 km → parcel no-go on 30 kg, **LTL** beats a van |
| `examples/full-truck.json` | 40 cases, 9.6 m³ → LTL over the 8 m³ cap, **14 ft truck** wins |

## Limits

- Screening cards, not a live rate shop: discounts, fuel, DIM divisors, and accessorials vary by carrier.
- FTL fit is cube × 85% and payload, not a 3D load plan (no stacking geometry).
- One shipment, one destination. Multi-stop, residential, liftgate, and appointment fees are out of scope.
- Great-circle km understate road km; pass `distance_km` when you know the lane.
