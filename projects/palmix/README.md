# PalMix

Mixed-store pallet builder for a grocery or case-pick dock.

PalMix is a deck-side “will these cases cube onto store pallets?” planner. You describe the pallet and the cases; it returns a placement list, leftover pieces, cube and weight fill, plus a local isometric deck map.

It is a planner, not a live WMS. Pallet sizes are typical working figures, not a particular pool spec sheet.

## How it works

1. **Expand.** A SKU with `quantity: 8` becomes eight physical cases.
2. **Sort.** **Auto** keeps a store together, seats non-crushable heavy cases first, then family. **Store** walks store ids. **Heavy** ignores store grouping for order (the lock still holds). **Compact** seats the smallest cube first so more cases find a gap.
3. **Store lock.** A pallet is stamped with the first case’s store and temperature. Later cases may top it off only when the store matches (unless `store_lock` is off) and the temp matches.
4. **Search corners.** Packing a pallet starts at `(0, 0, 0)`. After each placement, new candidate corners appear at the case’s +length, +width, and +height faces. Candidates are tried lowest first (z), then y, then x.
5. **Accept a pose** only if all of these hold:
   - The case stays inside the pallet envelope
   - It does not overlap a case already packed
   - It sits on the deck, or at least **70%** of its base rests on cases whose top is at that height
   - It does not sit on a `crushable` case
   - Adding its weight does not exceed payload
   - Adding build minutes does not blow the labor cap
6. **Open a pallet.** If nothing open can take it, PalMix starts a new pallet and spends `minutes_per_pallet`. Leftovers keep a reason (`temp`, `too-heavy`, `too-big`, `crush`, `labor-cap`, `pallet-cap`, `no-space`). Earlier seats are never pulled to help a later case.

Default labor is **8 minutes to open a pallet** and **1 minute per case**. A build can override `labor_minutes`.

### Deck presets

| Id | What | Inner L×W×H (mm) | Payload | Temp | Labor |
| --- | --- | --- | --- | --- | --- |
| `gma_48` | GMA 48×40 grocery | 1219×1016×1500 | 1000 kg | dry | 90 min |
| `eur` | EUR pallet | 1200×800×1440 | 1000 kg | dry | 90 min |
| `chep` | CHEP 48×40 | 1219×1016×1600 | 1250 kg | dry | 100 min |
| `chill_gma` | Chill GMA 48×40 | 1219×1016×1200 | 800 kg | chill | 60 min |

You can override payload, height, labor, or `max_pallets` on a preset, or pass a custom deck with `length_mm`, `width_mm`, `height_mm`, and `max_weight_kg`.

### Build file

```json
{
  "deck": { "preset": "gma_48" },
  "strategy": "auto",
  "labor_minutes": 90,
  "allow_rotation": true,
  "store_lock": true,
  "cases": [
    {
      "sku": "CEREAL-12",
      "store": "12",
      "family": "grocery",
      "temp": "dry",
      "length_mm": 400,
      "width_mm": 300,
      "height_mm": 280,
      "weight_kg": 6,
      "quantity": 8,
      "crushable": false
    }
  ]
}
```

Each `sku` + `store` pair must be unique. Temp is `dry`, `chill`, or `freeze`. Dimensions are millimetres; weight is kilograms per case.

## How to run

Needs **Python 3.10+**. No pip packages.

From this project folder (the staged copy in the factory repo is `projects/palmix`):

```bash
# List pallet decks
PYTHONPATH=src python3 -m palmix presets

# Mix an example (human-readable table)
PYTHONPATH=src python3 -m palmix mix examples/mixed-stores.json

# Same result as JSON
PYTHONPATH=src python3 -m palmix mix examples/mixed-stores.json --json

# Force a strategy
PYTHONPATH=src python3 -m palmix mix examples/store-lock.json --strategy store

# Local deck map
PYTHONPATH=src python3 -m palmix serve --host 127.0.0.1 --port 8782
```

Then open [http://127.0.0.1:8782](http://127.0.0.1:8782).

On the page:

1. Pick a pallet deck (default is the GMA 48×40) and a labor cap.
2. Edit the case table, or load `mixed-stores`, `store-lock`, `labor-capped`, or `too-heavy`.
3. Click **Mix pallets**. Packed count, pallet count, leftovers, and the isometric map update together.

CLI exit codes: `0` everything packed, `2` at least one case left behind, `1` usage or parse error.

### Optional install

```bash
pip install -e .
palmix mix examples/mixed-stores.json
palmix serve
```

### Tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Coverage includes side-by-side placement, stacking with support, store lock, crush-on-top, payload leftover, temp leftover, labor leftover, floor rotation, CLI exit codes, and the HTTP mix API.

## Examples

| File | What you should see |
| --- | --- |
| `examples/mixed-stores.json` | 24 dry cases onto two GMA pallets (store 12 and store 19), nothing left behind |
| `examples/store-lock.json` | Same SOAP sku for stores 04 and 21 → two EUR pallets |
| `examples/labor-capped.json` | 10-minute cap mixes `RICE-20` and leaves `BEANS-12` as `labor-cap` |
| `examples/too-heavy.json` | `ANVIL` is 55 kg on a 40 kg deck → leftover `too-heavy` |

## Limits

- Greedy mixer: good for a fast deck check, not a guaranteed optimal stack.
- Support is area-based, not a full physics engine (no crushing force, no wrap or corner-board rules).
- It does not print labels, reserve inventory, or drive a WMS.
