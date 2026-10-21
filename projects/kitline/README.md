# KitLine

Kitting-line planner for warehouse VAS and assembly cells.

KitLine is a line-side “which bench builds this work order?” planner. You describe the line, the kit catalog (with BOM), on-hand components, and the build wave; it returns one bench per build, leftover work orders, labor and bench fill, remaining inventory, plus a local line map.

It is a planner, not a WMS. Bench sizes are typical inner work envelopes, not a particular table brand. It does not print kit labels and it does not drive a pick-to-light rack.

## How it works

1. **Open the line.** A kitting line is a grid of equal workbenches. **Row 1 is the back wall.** The **aisle** row is the last row — closest to the walker pulling components. Columns sit left to right from the walker’s left. On a one-row line every bench is aisle.
2. **Catalog and explode.** Each kit SKU has finished-kit size/weight/temp and a BOM (`TEE ×1, MUG ×1, CARD ×1`). A build of `quantity: 6` needs six times every BOM line. One bench holds **one whole build**. Builds are never split across benches and benches never mix work orders.
3. **Sort the wave.** **Auto** and **priority** take hot builds first (`priority` 1), then the largest component-unit count (`BOM units × quantity`) so complex kits claim benches. **Family** groups the same kit SKU and fills left-to-right, top-to-bottom. **Compact** puts the smallest runs on first so more tickets get a bench.
4. **Accept a bench** only if all of these hold:
   - The finished kit’s three edges fit the bench (rotation allowed) and its cube stays inside
   - Finished-kit weight stays inside the bench
   - Kit temperature matches the line (`ambient` / `chill`), unless the line is `mixed`
   - Build quantity stays inside `max_run` (the bench will not stage an oversized run)
   - On-hand inventory covers every BOM line for the whole quantity
   - Adding `minutes_per_kit × quantity` does not blow the labor cap
   - An empty bench is still free
5. **Seat the build.** Auto prefers a bench next to the same kit SKU, then the aisle-facing cell. Inventory is decremented when the build seats, so a later twin can go `short`. Leftovers keep a reason (`temp`, `too-big`, `too-heavy`, `over-run`, `short`, `labor-cap`, `no-bench`). Earlier seats are never pulled to help a later build.

Because hot work claims the aisle first, the walker is not reaching over cold kits to grab same-day gift sets.

### Line presets

| Id | What | Grid | Bench L×W×H (mm) | Max kg | Max run | Temp | Labor |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `line_1x4` | Four-bench aisle | 1×4 | 600×500×400 | 12 | 12 | ambient | 2 min/kit + 48 min cap |
| `cell_2x3` | Two-row kitting cell | 2×3 | 700×600×450 | 18 | 16 | ambient | 3 min/kit + 90 min cap |
| `chill_1x3` | Meal-kit chill line | 1×3 | 650×500×400 | 10 | 10 | chill | 3 min/kit + 36 min cap |
| `mini_1x3` | Small demo line | 1×3 | 600×500×400 | 12 | 8 | mixed | 2 min/kit + 16 min cap |

You can override `rows`, `cols`, `length_mm`, `width_mm`, `height_mm`, `max_weight_kg`, `max_run`, `temp`, `minutes_per_kit`, or `max_labor_min` on a preset, or pass a custom line with those fields. A wave may also set `labor_minutes` to cap the clock without changing the preset.

Chill presets stay chill-only so yogurt cups do not sit on an ambient gift line. `mini_1x3` is mixed-temp for demos.

### Wave file

```json
{
  "line": { "preset": "cell_2x3" },
  "strategy": "auto",
  "inventory": [
    { "sku": "TEE", "on_hand": 30 },
    { "sku": "MUG", "on_hand": 20 }
  ],
  "kits": [
    {
      "sku": "GIFT-SET",
      "length_mm": 350,
      "width_mm": 280,
      "height_mm": 120,
      "weight_kg": 1.4,
      "temp": "ambient",
      "bom": [
        { "sku": "TEE", "quantity": 1 },
        { "sku": "MUG", "quantity": 1 }
      ]
    }
  ],
  "builds": [
    {
      "id": "WO-101",
      "kit_sku": "GIFT-SET",
      "quantity": 6,
      "priority": 1
    }
  ]
}
```

Each kit sku and build id must be unique. `priority` 1 is hottest (aisle first). Temp is `ambient` or `chill`. Dimensions are millimetres; weight is kilograms.

## How to run

Needs **Python 3.10+**. No pip packages.

From this project folder (the staged copy in the factory repo is `projects/kitline`):

```bash
# List kitting-line presets
PYTHONPATH=src python3 -m kitline presets

# Plan an example (human-readable table)
PYTHONPATH=src python3 -m kitline plan examples/gift-wave.json

# Same result as JSON
PYTHONPATH=src python3 -m kitline plan examples/gift-wave.json --json

# Force a strategy
PYTHONPATH=src python3 -m kitline plan examples/gift-wave.json --strategy family

# Local line map
PYTHONPATH=src python3 -m kitline serve --host 127.0.0.1 --port 8778
```

Then open [http://127.0.0.1:8778](http://127.0.0.1:8778).

On the page:

1. Pick a line (default is the 2×3 kitting cell), a strategy, and a labor cap.
2. Edit inventory, kits, and builds, or load `gift-wave`, `labor-capped`, `short-parts`, `too-big`, or `temp-mismatch`.
3. Click **Plan line**. Packed kits, benches, leftovers, remaining parts, and the aisle-row map update together.

CLI exit codes: `0` every build seated, `2` at least one leftover, `1` usage or parse error.

### Optional install

```bash
pip install -e .
kitline plan examples/gift-wave.json
kitline serve
```

### Tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Coverage includes aisle-row hot kits, same-SKU adjacency, compact small-first leftover, volume and edge too-big, too-heavy, over-run, labor cap, inventory short, temp mismatch, no-bench, BOM explosion, CLI exit codes, and the HTTP plan API.

## Examples

| File | What you should see |
| --- | --- |
| `examples/gift-wave.json` | 6 builds (27 kits) on a 2×3 ambient cell. WO-101 (hot GIFT-SET) sits at aisle R2C2, WO-102 (same kit) adjacent at R2C1. STARTER fills adjacent back benches. Nothing left behind. |
| `examples/labor-capped.json` | 3-kit WO-BIG takes 6 minutes of an 8-minute clock; WO-MID takes the last 2; WO-SMALL leftover `labor-cap` |
| `examples/short-parts.json` | WO-101 takes 4 TEE; WO-102 leftover `short` (needs 4 TEE, 2 left); WO-103 STARTER still seats |
| `examples/too-big.json` | STARTER seats. POSTER-KIT leftover `too-big` (900 mm will not rotate into a 600 mm bench). HEAVY-KIT leftover `too-heavy`. LONG-RUN leftover `over-run` |
| `examples/temp-mismatch.json` | Ambient 1×4 takes two GIFT-SET builds. MEAL-KIT leftover `temp` even though it is priority 1 |

## Limits

- Greedy seater: good for a fast line-side check, not a guaranteed optimal mix of bench vs leftover.
- Fit is edge + cube + weight of one finished kit, not a 3D nest of components on the bench.
- Live scan guns, pick-to-light, and kit-label print are out of scope.
