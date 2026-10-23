# ChuteDrop

Sortation chute assigner for warehouse destination banks.

ChuteDrop is a sorter-side “which chute takes this carton?” planner. You describe the bank and the carton wave; it returns one chute per carton (many cartons share a destination), leftover recirculation, labor and chute fill, plus a local bank map.

It is a planner, not a WCS. Chute mouths are typical inner openings, not a particular sorter OEM. It does not fire divert arms and it does not print shipping labels.

## How it works

1. **Open the bank.** A sortation bank is a grid of equal chutes. **Row 1 is induction** — the first divert, shortest travel on the belt. The last row is the far bank. Columns sit left to right from the induction walker’s left. On a one-row bank every chute is induction.
2. **Lock a destination.** The first carton into an empty chute **locks that chute to its dest**. Later cartons for the same store/route top off that chute. A dest that overflows opens a second chute. Chutes never mix destinations.
3. **Sort the wave.** **Auto** takes hot cartons first (`priority` 1), then the largest cube so bulky freight claims a mouth before small parcels fill it. **Dest** groups destination codes and fills left-to-right, top-to-bottom. **Carrier** groups carrier then dest and keeps the same carrier in adjacent chutes. **Compact** puts the smallest cartons on first so more pieces divert.
4. **Accept a chute** only if all of these hold:
   - The carton’s three edges fit the mouth (rotation allowed) and its cube stays inside
   - Adding its weight stays inside the chute
   - Adding one more piece stays inside `max_cartons`
   - Carton temperature matches the bank (`ambient` / `chill`), unless the bank is `mixed`
   - The chute is empty, or already locked to this dest
   - Adding `minutes_per_carton` does not blow the labor cap
5. **Seat the carton.** Auto tops off an existing dest chute first, then opens the induction-closest empty mouth, preferring a cell next to the same dest. Leftovers keep a reason (`temp`, `too-big`, `too-heavy`, `labor-cap`, `chute-full`, `no-chute`). Earlier seats are never pulled to help a later carton.

Because hot stores claim induction first, the belt is not carrying same-day store freight to the far bank while a near chute sits empty.

### Bank presets

| Id | What | Grid | Mouth L×W×H (mm) | Max kg | Cap | Temp | Labor |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `bank_1x6` | Six-chute induction | 1×6 | 600×400×400 | 25 | 12 | mixed | 1 min/carton + 48 min cap |
| `bank_2x5` | Two-row sorter bank | 2×5 | 550×380×380 | 20 | 10 | mixed | 1 min/carton + 80 min cap |
| `chill_1x4` | Grocery chill sorter | 1×4 | 500×350×350 | 15 | 8 | chill | 1 min/carton + 24 min cap |
| `mini_1x3` | Small demo bank | 1×3 | 600×400×400 | 18 | 6 | mixed | 1 min/carton + 12 min cap |

You can override `rows`, `cols`, `length_mm`, `width_mm`, `height_mm`, `max_weight_kg`, `max_cartons`, `temp`, `minutes_per_carton`, or `max_labor_min` on a preset, or pass a custom bank with those fields. A wave may also set `labor_minutes` to cap the clock without changing the preset.

Chill presets stay chill-only so yogurt totes do not divert into an ambient parcel chute. `mini_1x3` and the mixed banks take both temps.

### Wave file

```json
{
  "bank": { "preset": "bank_2x5" },
  "strategy": "auto",
  "cartons": [
    {
      "id": "C-121",
      "dest": "STORE-12",
      "carrier": "OWN",
      "length_mm": 400,
      "width_mm": 300,
      "height_mm": 200,
      "weight_kg": 5.0,
      "temp": "ambient",
      "priority": 1
    }
  ]
}
```

Each carton id must be unique. `priority` 1 is hottest (induction first). Temp is `ambient` or `chill`. Dimensions are millimetres; weight is kilograms.

## How to run

Needs **Python 3.10+**. No pip packages.

From this project folder (the staged copy in the factory repo is `projects/chutedrop`):

```bash
# List sortation-bank presets
PYTHONPATH=src python3 -m chutedrop presets

# Plan an example (human-readable table)
PYTHONPATH=src python3 -m chutedrop plan examples/store-wave.json

# Same result as JSON
PYTHONPATH=src python3 -m chutedrop plan examples/store-wave.json --json

# Force a strategy
PYTHONPATH=src python3 -m chutedrop plan examples/store-wave.json --strategy dest

# Local bank map
PYTHONPATH=src python3 -m chutedrop serve --host 127.0.0.1 --port 8779
```

Then open [http://127.0.0.1:8779](http://127.0.0.1:8779).

On the page:

1. Pick a bank (default is the 2×5 sorter), a strategy, and a labor cap.
2. Edit the carton table, or load `store-wave`, `labor-capped`, `chute-full`, `too-big`, or `temp-mismatch`.
3. Click **Plan bank**. Packed cartons, dests, leftovers, and the induction-row map update together.

CLI exit codes: `0` every carton diverted, `2` at least one leftover, `1` usage or parse error.

### Optional install

```bash
pip install -e .
chutedrop plan examples/store-wave.json
chutedrop serve
```

### Tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Coverage includes induction hot dests, same-dest top-off, dest raster blocks, carrier adjacency, compact small-first leftover, volume and edge too-big, too-heavy, labor cap, chute-full, temp mismatch, no-chute, CLI exit codes, and the HTTP plan API.

## Examples

| File | What you should see |
| --- | --- |
| `examples/store-wave.json` | 14 cartons / 5 dests on a 2×5 mixed bank. STORE-12 (largest hot dest) locks induction R1C3; STORE-08 adjacent at R1C2. STORE-21 / 04 / 33 fill the rest of the induction row. Nothing left behind. |
| `examples/labor-capped.json` | 4 cartons take a 4-minute clock on `mini_1x3`; C-5 and C-6 leftover `labor-cap` |
| `examples/chute-full.json` | STORE-99 fills three chutes at 2 cartons each; C-7 leftover `chute-full` |
| `examples/too-big.json` | C-OK seats. C-POLE leftover `too-big` (900 mm will not rotate into a 600 mm mouth). C-HEAVY leftover `too-heavy` |
| `examples/temp-mismatch.json` | Chill 1×4 takes two STORE-G1 totes. C-DRY leftover `temp` even though it is priority 1 |

## Limits

- Greedy seater: good for a fast sorter-side check, not a guaranteed optimal mix of chute vs recirculate.
- Fit is edge + cube + weight of one carton against the mouth, not a 3D nest inside the chute bag.
- Live divert photo-eyes, recirculation loops, and label print are out of scope.
