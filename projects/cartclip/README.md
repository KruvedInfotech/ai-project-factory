# CartClip

Pick-cart cluster planner for a warehouse order wave.

CartClip is a floor-side “which tickets share this walk?” planner. You describe the floor, the cart, and the orders; it clips one order per tote, lists leftovers, and draws a local cart / aisle map.

It is a planner, not a live WMS. Tote counts and aisle spans are working figures, not a particular cart OEM.

## How it works

1. **One tote, one order.** A pick cart is a row of totes. CartClip never splits an order across carts and never mixes two orders in one tote.
2. **Sort the wave.** **Auto** takes hot tickets first (`priority` 1), then the most lines. **Aisle** walks the floor A→Z and only tops off a cart that already visits that aisle. **Priority** ignores clustering. **Compact** seats the smallest cube first so more tickets get a tote.
3. **Top off.** An order tries open same-temp carts first. The best host is the one that already shares the most aisles (Jaccard), then the fullest cart.
4. **Accept a tote** only if all of these hold:
   - A tote slot is still free
   - Combined weight stays inside the cart
   - Combined cube stays inside the cart
   - Order temperature matches the cart (`dry` / `chill` / `freeze`), unless the cart is `mixed`
   - Combined aisle span (last aisle index minus first) stays inside `max_aisle_span`
   - Adding clip + pick minutes does not blow the labor cap
5. **Open a cart.** If nothing open can take it, CartClip starts a new cart and spends `minutes_per_cart`. Leftovers keep a reason (`temp`, `too-heavy`, `too-cube`, `aisle-span`, `labor-cap`). Earlier seats are never pulled to help a later order.

Default labor is **6 minutes to open a cart**, **1 minute to clip an order**, and **1 minute per pick line**. A wave can override `labor_minutes`.

### Floor presets

| Id | What | Aisles × bays |
| --- | --- | --- |
| `small_dc` | 4-aisle case pick | A–D × 10 |
| `grocery` | 6-aisle grocery | A–F × 12 |
| `ecom` | 8-aisle each-pick | A–H × 16 |

### Cart presets

| Id | What | Totes | Payload | Cube | Temp | Span | Labor |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `ecom_8tote` | Each-pick cart | 8 | 45 kg | 80 L | dry | 3 | 90 min |
| `grocery_4tote` | Grocery case cart | 4 | 90 kg | 160 L | dry | 2 | 60 min |
| `chill_6tote` | Chill cart | 6 | 50 kg | 70 L | chill | 4 | 48 min |

You can override tote count, payload, cube, span, or labor on a preset, or pass a custom cart with `tote_slots`, `max_weight_kg`, and `max_volume_l`.

### Wave file

```json
{
  "warehouse": { "preset": "small_dc" },
  "cart": { "preset": "ecom_8tote" },
  "strategy": "auto",
  "labor_minutes": 90,
  "orders": [
    {
      "id": "ORD-101",
      "priority": 1,
      "temp": "dry",
      "lines": [
        {
          "sku": "TEE-BLK-M",
          "aisle": "A",
          "bay": 2,
          "quantity": 2,
          "length_mm": 220,
          "width_mm": 160,
          "height_mm": 40,
          "weight_kg": 0.35
        }
      ]
    }
  ]
}
```

Each order id must be unique. `priority` 1 is hottest. Temp is `dry`, `chill`, or `freeze`. Dimensions are millimetres; weight is kilograms per unit.

## How to run

Needs **Python 3.10+**. No pip packages.

From this project folder (the staged copy in the factory repo is `projects/cartclip`):

```bash
# List floors and carts
PYTHONPATH=src python3 -m cartclip presets

# Clip an example (human-readable table)
PYTHONPATH=src python3 -m cartclip clip examples/mixed-wave.json

# Same result as JSON
PYTHONPATH=src python3 -m cartclip clip examples/mixed-wave.json --json

# Force a strategy
PYTHONPATH=src python3 -m cartclip clip examples/aisle-cluster.json --strategy aisle

# Local cart / aisle map
PYTHONPATH=src python3 -m cartclip serve --host 127.0.0.1 --port 8781
```

Then open [http://127.0.0.1:8781](http://127.0.0.1:8781).

On the page:

1. Pick a floor (default is the 4-aisle case pick) and a cart.
2. Edit the order table, or load `mixed-wave`, `aisle-cluster`, `labor-capped`, or `too-heavy`.
3. Click **Clip carts**. Carts, leftovers, tote fill, and the aisle map update together.

CLI exit codes: `0` every order clipped, `2` at least one order left behind, `1` usage or parse error.

### Optional install

```bash
pip install -e .
cartclip clip examples/mixed-wave.json
cartclip serve
```

### Tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Coverage includes same-aisle top-off, aisle-span splits, payload leftover, temp leftover, labor leftover, tote overflow, CLI exit codes, and the HTTP clip API.

## Examples

| File | What you should see |
| --- | --- |
| `examples/mixed-wave.json` | 4 dry tickets on the 8-tote cart, one walk across A and B, nothing left behind |
| `examples/aisle-cluster.json` | Aisle strategy keeps A-aisle grocery with A, and D on a second cart |
| `examples/labor-capped.json` | 10-minute cap clips `ORD-HOT` and leaves `ORD-NEXT` as `labor-cap` |
| `examples/too-heavy.json` | `ORD-ANVIL` is 52 kg on a 45 kg cart → leftover `too-heavy` |

## Limits

- Greedy clipper: good for a fast floor check, not a guaranteed optimal cluster.
- Aisle span is index distance, not walking metres or congestion.
- It does not print labels, reserve inventory, or drive a WMS.
