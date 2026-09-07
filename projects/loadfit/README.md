# LoadFit

3D carton packer for a van, truck, or shipping container.

LoadFit is a dock-side “will it cube?” planner. You describe the cargo box and the cartons; it returns a placement list, leftover pieces, cube and weight fill, plus a local isometric map.

It is a planner, not a live TMS. Vehicle sizes are typical inner dimensions, not a particular OEM spec sheet.

## How it works

1. **Expand.** A SKU with `quantity: 8` becomes eight physical pieces.
2. **Sort.** Largest pieces first (longest edge, then volume, then weight) so bulky cartons claim space before small ones fill gaps.
3. **Search corners.** Packing starts at the origin `(0, 0, 0)`. After each placement, new candidate corners appear at the carton’s +length, +width, and +height faces. Candidates are tried lowest first (z), then y, then x — deepest, bottom, left.
4. **Rotate.** With rotation on and “this side up”, only length and width swap. Turning that off allows full 3D tumbling.
5. **Accept a pose** only if all of these hold:
   - The carton stays inside the cargo box
   - It does not overlap a carton already packed
   - It sits on the floor, or at least **70%** of its base rests on cartons whose top is at that height (no floating stacks)
   - Adding its weight does not exceed payload
6. **Leftovers.** Pieces that fail those checks are listed as unpacked. The process is greedy: it will not unpack an earlier carton to make a later one fit.

### Vehicle presets

| Id | What | Inner L×W×H (mm) | Payload (kg) |
| --- | --- | --- | --- |
| `van_407` | Light truck / 407-class | 2740×1800×1800 | 2500 |
| `truck_14ft` | 14 ft box truck | 4270×2130×2130 | 4000 |
| `truck_20ft` | 20 ft box truck | 6100×2130×2280 | 7000 |
| `container_20ft` | 20 ft dry container | 5898×2352×2393 | 21700 |
| `container_40ft` | 40 ft dry container | 12032×2352×2393 | 26600 |
| `pallet_eu` | EUR pallet stack | 1200×800×1440 | 1000 |

You can override `max_weight_kg` on a preset, or pass a custom box with `length_mm`, `width_mm`, `height_mm`, and `max_weight_kg`.

### Shipment file

```json
{
  "container": { "preset": "truck_14ft" },
  "allow_rotation": true,
  "this_side_up": true,
  "boxes": [
    {
      "sku": "A-CARTON",
      "length_mm": 600,
      "width_mm": 400,
      "height_mm": 350,
      "weight_kg": 14,
      "quantity": 10
    }
  ]
}
```

Each SKU must be unique. Dimensions are millimetres; weight is kilograms.

## How to run

Needs **Python 3.10+**. No pip packages.

From this project folder (the staged copy in the factory repo is `projects/loadfit`):

```bash
# List cargo-box presets
PYTHONPATH=src python3 -m loadfit presets

# Pack an example (human-readable table)
PYTHONPATH=src python3 -m loadfit pack examples/mixed-cartons.json

# Same result as JSON
PYTHONPATH=src python3 -m loadfit pack examples/mixed-cartons.json --json

# Local load map
PYTHONPATH=src python3 -m loadfit serve --host 127.0.0.1 --port 8765
```

Then open [http://127.0.0.1:8765](http://127.0.0.1:8765).

On the page:

1. Pick a cargo box (default is the 14 ft truck) and a payload cap.
2. Edit the carton table, or load `mixed-cartons`, `pallet-cases`, or `payload-capped`.
3. Click **Pack load**. Packed count, cube %, weight %, leftovers, and the isometric map update together.

CLI exit codes: `0` everything packed, `2` at least one carton left behind, `1` usage or parse error.

### Optional install

```bash
pip install -e .
loadfit pack examples/pallet-cases.json
loadfit serve
```

### Tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Coverage includes side-by-side placement, stacking with support, floor rotation, payload leftover, overlap/bounds checks, CLI exit codes, and the HTTP pack API.

## Examples

| File | What you should see |
| --- | --- |
| `examples/mixed-cartons.json` | 24 cartons into a 14 ft truck, nothing left behind |
| `examples/pallet-cases.json` | 8 identical cases on a EUR pallet, including a second layer |
| `examples/payload-capped.json` | 4× HEAVY into a van capped at 40 kg → 2 packed, 2 left behind |

## Limits

- Greedy packer: good for a fast dock check, not a guaranteed optimal load.
- Support is area-based, not a full physics engine (no crushing, no stability beyond the 70% rule).
- Factors such as axle limits, load bars, and dunnage are out of scope.
