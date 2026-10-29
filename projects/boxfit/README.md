# BoxFit

Shipper cartonization planner for a pack station.

BoxFit is a bench-side “which box?” planner. You describe a shipper catalog and the order lines; it opens the smallest legal carton, tops off same-order same-temp pieces, lists leftovers, and draws a local carton map.

It is a planner, not a live WMS. Carton sizes are inner working figures, not a particular corrugate spec sheet.

## How it works

1. **Expand.** A line with `quantity: 4` becomes four physical pieces.
2. **Sort.** Within each order, largest pieces first (longest edge, then volume, then weight) so bulky items claim a carton before small ones fill gaps.
3. **One order, one temp.** A carton never mixes orders. Chill does not ride with dry.
4. **Top off.** A piece tries already-open cartons of that order and temperature, fullest first. It must stay inside the inner box, not overlap, sit on the floor or on ≥70% support, and stay under payload.
5. **Open smallest.** If nothing open can take it, BoxFit opens the smallest catalog shipper (by inner volume) that can hold this piece in a legal pose. Opening a carton spends pack minutes.
6. **Rotate.** With rotation on and “this side up”, only length and width swap. Turning that off allows full 3D tumbling.
7. **Leftovers.** Pieces that fail those checks are listed as unpacked with a reason (`too-big`, `too-heavy`, `labor cap`). The process is greedy: it will not unpack an earlier carton to make a later one fit.

Default labor is **2 minutes to open a carton** and **1 minute per piece**. A plan can override `minutes_per_carton` and `minutes_per_piece`.

### Catalog presets

| Id | What | Shippers |
| --- | --- | --- |
| `ecom_pack` | E-com pack bench | mailer S/M/L, small cube, #4, #6 |
| `parcel_dc` | Parcel DC corrugate | #4, #6, #12, #18, #24 RSC |
| `grocery_shipper` | Grocery store shipper | half / full shipper, crate, #12 |

You can pass a custom catalog with a `cartons` list (`id`, `length_mm`, `width_mm`, `height_mm`, `max_weight_kg`).

### Plan file

```json
{
  "catalog": { "preset": "ecom_pack" },
  "labor_minutes": 60,
  "allow_rotation": true,
  "this_side_up": true,
  "items": [
    {
      "order_id": "O-4412",
      "sku": "BOOK-A",
      "length_mm": 200,
      "width_mm": 130,
      "height_mm": 18,
      "weight_kg": 0.3,
      "quantity": 4,
      "temp": "dry"
    }
  ]
}
```

Each SKU must be unique inside an order. Dimensions are millimetres; weight is kilograms. `temp` is `dry`, `chill`, or `freeze`.

## How to run

Needs **Python 3.10+**. No pip packages.

From this project folder (the staged copy in the factory repo is `projects/boxfit`):

```bash
# List shipper catalogs
PYTHONPATH=src python3 -m boxfit presets

# Pack an example (human-readable table)
PYTHONPATH=src python3 -m boxfit pack examples/mixed-order.json

# Same result as JSON
PYTHONPATH=src python3 -m boxfit pack examples/mixed-order.json --json

# Local carton map
PYTHONPATH=src python3 -m boxfit serve --host 127.0.0.1 --port 8780
```

Then open [http://127.0.0.1:8780](http://127.0.0.1:8780).

On the page:

1. Pick a shipper catalog (default is the e-com pack bench) and a labor cap.
2. Edit the item table, or load `mixed-order`, `split-orders`, `too-big`, or `labor-capped`.
3. Click **Fit cartons**. Carton count, packed pieces, mean void, leftovers, and the isometric map update together.

CLI exit codes: `0` everything packed, `2` at least one piece left behind, `1` usage or parse error.

### Optional install

```bash
pip install -e .
boxfit pack examples/mixed-order.json
boxfit serve
```

### Tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Coverage includes smallest-carton choice, same-order top-off, order/temp isolation, this-side-up vs tumble, payload leftover, labor leftover, CLI exit codes, and the HTTP pack API.

## Examples

| File | What you should see |
| --- | --- |
| `examples/mixed-order.json` | Books, tees, and mugs for one order into e-com shippers, nothing left behind |
| `examples/split-orders.json` | Two parcel orders, never sharing a carton |
| `examples/too-big.json` | A lamp that no e-com shipper can hold → leftover `too-big`; the book still packs |
| `examples/labor-capped.json` | Three mugs with a 3-minute clock → first mug packed, the rest `labor cap` |

## Limits

- Greedy cartonizer: good for a fast pack-bench check, not a guaranteed minimum carton count.
- Support is area-based, not a full physics engine (no crushing, no dunnage).
- Carrier dim-weight, void fill, and print-and-apply are out of scope.
