# LoadFit

Pack cartons into a van, truck, or shipping container.

LoadFit is a small 3D bin packer for dispatch desks that need a quick “will it cube?” check before a vehicle leaves the dock. It keeps cartons inside the cargo box, refuses overlaps, stacks only when a piece has enough support underneath, and stops when payload is gone.

This is a planner, not a live TMS. Treat the vehicle sizes as working interiors, not a particular OEM spec.

## What it does

- Greedy deepest-bottom-left packing, largest cartons first
- Floor rotation (keep “this side up”) or full 3D tumbling
- Payload cap so a light, bulky load is not treated the same as a dense one
- Presets for a 407-class van, 14/20 ft trucks, 20/40 ft dry containers, and a EUR pallet
- CLI report plus a local isometric load map

## Run

From this folder, no extra packages:

```bash
PYTHONPATH=src python3 -m loadfit presets
PYTHONPATH=src python3 -m loadfit pack examples/mixed-cartons.json
PYTHONPATH=src python3 -m loadfit pack examples/mixed-cartons.json --json
PYTHONPATH=src python3 -m loadfit serve --host 127.0.0.1 --port 8765
```

Then open `http://127.0.0.1:8765`.

Exit code `2` means at least one carton did not fit.

## Shipment file

```json
{
  "container": { "preset": "truck_14ft" },
  "allow_rotation": true,
  "this_side_up": true,
  "boxes": [
    { "sku": "A-CARTON", "length_mm": 600, "width_mm": 400, "height_mm": 350, "weight_kg": 14, "quantity": 10 }
  ]
}
```

`container` can also be a custom inner box: `length_mm`, `width_mm`, `height_mm`, `max_weight_kg`.

## Tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```
