# WallSort

Put-to-wall cubby sorter for batch-picked warehouse orders.

WallSort is a pack-station “which cubby is this order?” planner. You describe the wall and the orders; it returns one cubby per order, leftover units, labor and cubby fill, plus a local wall map.

It is a planner, not a WMS. Cubby sizes are typical inner openings, not a particular fixture brand. It does not print labels and it does not drive a sorter.

## How it works

1. **Open the wall.** A put-wall is a grid of equal cubbies. **Row 1 is the top** (stretch). The **waist** row is the golden zone — easiest reach for the packer standing in front. The bottom row is a stoop. Two columns or more sit left to right from the packer’s left.
2. **Expand.** A line with `quantity: 2` becomes two physical units (`ORD-101-L1-1`, `ORD-101-L1-2`). One cubby holds **one whole order**. Orders are never split across cubbies and cubbies never mix orders.
3. **Sort the wave.** **Auto** and **priority** take hot orders first (`priority` 1), then the largest cube. **Carrier** groups the same shipper together and fills left-to-right, top-to-bottom. **Compact** puts the smallest orders on first so more tickets get a cubby.
4. **Accept a cubby** only if all of these hold:
   - Every unit’s three edges fit the cubby (rotation allowed)
   - Combined cube stays inside the cubby
   - Combined weight stays inside the cubby
   - Unit temperature matches the wall (`ambient` / `chill`), unless the wall is `mixed`
   - Adding `minutes_per_unit` for each piece does not blow the labor cap
   - An empty cubby is still free
5. **Seat the order.** Auto prefers a cubby next to the same carrier, then the golden (waist) cell. Priority ignores carrier and always takes the closest waist cubby. Leftovers keep a reason (`temp`, `too-big`, `too-heavy`, `labor-cap`, `no-cubby`). Earlier seats are never pulled to help a later order.

Because hot work claims the waist row first, the packer is not reaching over cold orders to grab same-day tickets.

### Wall presets

| Id | What | Grid | Cubby L×W×H (mm) | Max kg | Temp | Labor |
| --- | --- | --- | --- | --- | --- | --- |
| `wall_3x4` | Standard pack wall | 3×4 | 400×300×350 | 8 | ambient | 1 min/unit + 30 min cap |
| `pack_2x6` | Low pack bench | 2×6 | 350×250×300 | 6 | ambient | 1 min/unit + 20 min cap |
| `chill_2x4` | Chill wall | 2×4 | 450×350×400 | 12 | chill | 1 min/unit + 16 min cap |
| `mini_2x3` | Small demo wall | 2×3 | 400×300×350 | 8 | mixed | 1 min/unit + 8 min cap |

You can override `rows`, `cols`, `length_mm`, `width_mm`, `height_mm`, `max_weight_kg`, `temp`, `minutes_per_unit`, or `max_labor_min` on a preset, or pass a custom wall with those fields. A batch may also set `labor_minutes` to cap the clock without changing the preset.

Chill presets stay chill-only so gel packs do not sit on an ambient wall. `mini_2x3` is mixed-temp for demos.

### Batch file

```json
{
  "wall": { "preset": "wall_3x4" },
  "strategy": "auto",
  "orders": [
    {
      "id": "ORD-101",
      "carrier": "UPS",
      "priority": 1,
      "lines": [
        {
          "sku": "TEE",
          "length_mm": 250,
          "width_mm": 180,
          "height_mm": 60,
          "weight_kg": 0.4,
          "temp": "ambient",
          "quantity": 2
        }
      ]
    }
  ]
}
```

Each order id must be unique. `priority` 1 is hottest (waist row first). Temp is `ambient` or `chill`. Dimensions are millimetres; weight is kilograms.

## How to run

Needs **Python 3.10+**. No pip packages.

From this project folder (the staged copy in the factory repo is `projects/wallsort`):

```bash
# List put-wall presets
PYTHONPATH=src python3 -m wallsort presets

# Sort an example (human-readable table)
PYTHONPATH=src python3 -m wallsort sort examples/batch-wave.json

# Same result as JSON
PYTHONPATH=src python3 -m wallsort sort examples/batch-wave.json --json

# Force a strategy
PYTHONPATH=src python3 -m wallsort sort examples/batch-wave.json --strategy carrier

# Local wall map
PYTHONPATH=src python3 -m wallsort serve --host 127.0.0.1 --port 8777
```

Then open [http://127.0.0.1:8777](http://127.0.0.1:8777).

On the page:

1. Pick a wall (default is the 3×4 pack wall), a strategy, and a labor cap.
2. Edit the order table, or load `batch-wave`, `labor-capped`, `too-big`, or `temp-mismatch`.
3. Click **Sort wall**. Packed count, cubbies, leftovers, and the waist-row map update together.

CLI exit codes: `0` every unit seated, `2` at least one leftover, `1` usage or parse error.

### Optional install

```bash
pip install -e .
wallsort sort examples/batch-wave.json
wallsort serve
```

### Tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Coverage includes waist-row hot orders, same-carrier adjacency, compact small-first leftover, volume and edge too-big, too-heavy, labor cap, temp mismatch, no-cubby, quantity expansion, CLI exit codes, and the HTTP sort API.

## Examples

| File | What you should see |
| --- | --- |
| `examples/batch-wave.json` | 8 orders (10 units) on a 3×4 ambient wall. ORD-102 (hot FedEx) sits at waist R2C2, ORD-101 (hot UPS) at R2C3. UPS fills adjacent cubbies. Nothing left behind. |
| `examples/labor-capped.json` | 2-unit ORD-BIG takes 2 minutes of a 3-minute clock; ORD-MID takes the last minute; ORD-SMALL leftover `labor-cap` |
| `examples/too-big.json` | TEE seats. POSTER-TUBE leftover `too-big` (900 mm will not rotate into a 400 mm cubby). DUMBBELL leftover `too-heavy` |
| `examples/temp-mismatch.json` | Ambient 3×4 takes TEE, CAP, and BOOK. GEL-PACK leftover `temp` even though it is priority 1 |

## Limits

- Greedy seater: good for a fast pack-station check, not a guaranteed optimal mix of cubby vs leftover.
- Fit is edge + cube + weight, not a full 3D packer (no crushing, no dunnage).
- Live scan guns, cartonization, and carrier rate shop are out of scope.
