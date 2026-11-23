# HazPad

Hazmat segregation desk for a warehouse pad or trailer.

HazPad is a dock-side “can these share the box?” screen. You describe the pad and the lots; it returns a bay map, leftover drums, and every pair’s mixing code.

It is a planner, not a live dangerous-goods system. The grid is an IMDG-inspired warehouse screen, not a certified copy of IMDG 7.2 or 49 CFR 177.848.

## How it works

1. **Class.** Each lot has a UN class (`2.1` … `9`) or `FOOD`. A known UN number (1203, 1263, 2014, 3480, …) fills class and description if you omit them. `foodstuff: true` also applies the food row — bleach next to wine is forbidden even if the wine is class 3.
2. **Mix.** Every pair looks up a code:
   - **C** compatible — adjacent bays are fine
   - **A** away from — leave `away_bays` empty between them (default 1, so they sit at least two bays apart)
   - **S** separated — other compartment, or an empty bay if `empty_as_partition` is on
   - **X** forbidden — they cannot share this pad or trailer
3. **Limited quantity.** When both lots are `limited_qty` and both classes are in `3 / 4.1 / 5.1 / 6.1 / 8 / 9`, the screen eases **X → S** and **S → A**. Toxic gas, 4.2, 4.3, 5.2, and food never ease.
4. **Place.** Heaviest lot first. Each lot takes the lowest-index empty bay that honours every code against lots already on the pad. An empty bay that is holding an S partition is not reused. Lots that fail every bay are leftover (next trailer).
5. **Compartments.** With `compartments: 2`, the front half of the bays is compartment 0 and the rest is 1. An S pair may sit on either side of that bulkhead even if the bays are adjacent.

### Shipment file

```json
{
  "pad": {
    "id": "PAD-A",
    "bays": 8,
    "compartments": 1,
    "away_bays": 1,
    "empty_as_partition": true
  },
  "allow_limited_qty_ease": true,
  "lots": [
    {
      "lot": "GAS-01",
      "un": "1203",
      "class": "3",
      "description": "Gasoline",
      "kg": 800,
      "limited_qty": false,
      "foodstuff": false
    }
  ]
}
```

Lot ids must be unique. Weight is kilograms. Class is required unless `un` is a known preset.

### Mixing grid (short)

|  | 2.1 | 3 | 5.1 | 6.1 | 8 | 9 | FOOD |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **2.1** | C | A | X | A | A | C | A |
| **3** | A | C | X | A | A | C | A |
| **5.1** | X | X | A | S | S | A | A |
| **8** | A | A | S | A | C | C | X |
| **FOOD** | A | A | A | X | X | C | C |

`python3 -m hazpad classes` prints the full 13×13 grid.

## How to run

Needs **Python 3.10+**. No pip packages.

From this project folder (the staged copy in the factory repo is `projects/hazpad`):

```bash
# List classes and the mixing grid
PYTHONPATH=src python3 -m hazpad classes

# Check an example (human-readable pad map)
PYTHONPATH=src python3 -m hazpad check examples/compatible-mix.json

# Same result as JSON
PYTHONPATH=src python3 -m hazpad check examples/oxidizer-clash.json --json

# Local segregation desk
PYTHONPATH=src python3 -m hazpad serve --host 127.0.0.1 --port 8796
```

Then open [http://127.0.0.1:8796](http://127.0.0.1:8796).

On the page:

1. Load `compatible-mix`, `oxidizer-clash`, `away-food`, `two-compartment`, or `limited-qty`, or edit the lot table.
2. Set bays, compartments, away spacing, and the LQ / empty-partition flags.
3. Click **Check pad**. Placed count, on-pad kg, worst code, leftover, the bay map, and the pair table update together.

CLI exit codes: `0` every lot staged, `2` at least one lot left behind, `1` usage or parse error.

### Optional install

```bash
pip install -e .
hazpad check examples/compatible-mix.json
hazpad serve
```

### Tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Coverage includes the mixing grid, oxidizer leftover, food spacing, two-compartment bulkhead, LQ ease vs no-ease, partition hold, food-flag overlay, heaviest-first, CLI exit codes, and the HTTP check API.

## Examples

| File | What you should see |
| --- | --- |
| `examples/compatible-mix.json` | Gasoline + lithium batteries + nitrogen on 8 bays → **all placed** in bays 0–2 (exit 0) |
| `examples/oxidizer-clash.json` | Gasoline keeps the trailer; **H2O2 leftover** (3 × 5.1 is X); class 9 still loads (exit 2) |
| `examples/away-food.json` | Produce in bay 0, paint in bay **2** (class 3 is away-from food) |
| `examples/two-compartment.json` | Flammable aerosols in front, toxic gas **rear of the bulkhead** (S, empty bay is not a partition) |
| `examples/limited-qty.json` | LQ paint + LQ peroxide: raw X eases to S → bays **0 and 2** |

## Limits

- One pad, unique lots, one bay per lot. No stacking, no split drums, no multi-pad routing.
- The grid is a warehouse screen (typical class pairs), not packing-group, subsidiary-risk, or UN-number exceptions.
- Limited-quantity ease is a local rule, not an IMDG LQ chapter.
- Axle weights, placarding, and driver paperwork are out of scope.
