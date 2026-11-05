# StageLane

Outbound staging-lane planner for a dock.

StageLane is a dock-side “will these pallets sit?” planner. You describe the painted lanes and the pallets; it seats each one into a bay, lists leftovers, and draws a local yard map.

It is a planner, not a live WMS. Lane lengths and floor loads are working figures, not a particular warehouse drawing.

PalMix builds the pallet. StopStack loads the trailer. DockBook books the door. StageLane is the strip of floor in between: one carrier per bay, a matching door, and a cutoff that does not steal a slot from a pallet already seated.

## How it works

1. **Sort the wave.** **Auto** takes hot tickets first (`priority` 1), then soonest departure, then heaviest. **Cutoff** walks the clock. **Cluster** groups by carrier then door. **Compact** seats the shortest pallet first so more pieces fit.
2. **Claim a bay.** Each pallet wants an open lane. StageLane tops off a lane that already holds that carrier (and door) before it opens an empty bay. With stacking on, a matching pallet can sit on the last deck instead of eating more length.
3. **Accept a seat** only if all of these hold:
   - The lane exists and matches the pallet temperature (`dry` / `chill` / `freeze`, unless the lane is `mixed`)
   - Remaining length covers the pallet (a stack does not consume extra length)
   - Remaining floor load covers the weight
   - Carrier matches the lane’s claim unless `mix_carriers` is on
   - Door matches the lane’s door unless `mix_doors` is on
   - A colder pallet on a warmer / mixed lane does not sit longer than `max_dwell_min`
   - Ready time is not after departure
   - Tug minutes still fit the labor cap
   - The yard still has a free pallet slot (`max_pallets`)
4. **Leftover.** Pieces that fail those checks keep a reason (`temp`, `too-heavy`, `too-long`, `dwell`, `cutoff`, `door`, `lane-full`, `carrier-mix`, `labor-cap`, `pallet-cap`). Earlier seats are never pulled to help a later pallet.

Default labor is **6 minutes to tug a pallet** on the grocery dock. A wave can override `labor_minutes`.

### Yard presets

| Id | What | Lanes | Length | Temp | Labor | Max pallets |
| --- | --- | --- | --- | --- | --- | --- |
| `grocery` | 6-lane grocery dock | L1–L6 doors 1–6 | 9600 mm | dry | 90 min | 48 |
| `parcel` | 4-lane parcel cages | P1–P4 doors 1–4 | 3600 mm | mixed | 60 min | 16 |
| `dc` | 4-lane store DC | S1–S4 doors 11–14 | 14400 mm | dry | 120 min | 48 |
| `chill` | 4-lane chill dock | C1–C4 doors 1–4 | 7200 mm | chill | 48 min | 24 |

You can override labor, `max_pallets`, or `max_dwell_min` on a preset, or pass a custom yard with a `lanes` list (`id`, `temp`, `length_mm`, `width_mm`, `max_weight_kg`, `max_height_mm`, `door`).

### Wave file

```json
{
  "yard": { "preset": "grocery" },
  "strategy": "auto",
  "labor_minutes": 90,
  "mix_carriers": false,
  "mix_doors": false,
  "allow_stack": false,
  "pallets": [
    {
      "id": "PAL-11",
      "carrier": "UPS",
      "priority": 1,
      "temp": "dry",
      "door": 1,
      "length_mm": 1200,
      "width_mm": 1000,
      "height_mm": 1400,
      "weight_kg": 420,
      "depart_min": 90
    }
  ]
}
```

Each pallet id must be unique. `priority` 1 is hottest. Temp is `dry`, `chill`, or `freeze`. Carrier codes are uppercased. Dimensions are millimetres; weight is kilograms.

## How to run

Needs **Python 3.10+**. No pip packages.

From this project folder (the staged copy in the factory repo is `projects/stagelane`):

```bash
# List staging yards
PYTHONPATH=src python3 -m stagelane presets

# Seat an example (human-readable table)
PYTHONPATH=src python3 -m stagelane seat examples/clear-yard.json

# Same result as JSON
PYTHONPATH=src python3 -m stagelane seat examples/clear-yard.json --json

# Force a strategy
PYTHONPATH=src python3 -m stagelane seat examples/lane-full.json --strategy compact

# Local dock map
PYTHONPATH=src python3 -m stagelane serve --host 127.0.0.1 --port 8784
```

Then open [http://127.0.0.1:8784](http://127.0.0.1:8784).

On the page:

1. Pick a yard (default is grocery) and a labor cap.
2. Edit the pallet table, or load `clear-yard`, `lane-full`, `labor-capped`, or `temp-block`.
3. Click **Seat yard**. Seated count, leftovers, labor, and the dock map update together.

CLI exit codes: `0` every pallet seated, `2` at least one pallet left behind, `1` usage or parse error.

### Optional install

```bash
pip install -e .
stagelane seat examples/clear-yard.json
stagelane serve
```

### Tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Coverage includes same-carrier top-off, carrier exclusive, door leftover, lane-full leftover, stacking, dwell, temp leftover, labor leftover, cutoff leftover, CLI exit codes, and the HTTP seat API.

## Examples

| File | What you should see |
| --- | --- |
| `examples/clear-yard.json` | 4 dry pallets on grocery L1–L6, nothing left behind. PAL-11 and PAL-12 share door 1 / lane L1 |
| `examples/lane-full.json` | One 2400 mm parcel lane takes two 1200 mm cages. CAG-03 is leftover `lane-full` |
| `examples/labor-capped.json` | 6-minute cap seats `PAL-31` and leaves `PAL-32` as `labor-cap` |
| `examples/temp-block.json` | Chill dock seats `PAL-40` and leaves dry `PAL-41` as `temp` |

## Limits

- Greedy seater: good for a fast dock check, not a guaranteed optimal assignment.
- Lanes are a snapshot. It does not free a bay when a trailer actually pulls.
- It does not drive tugs, print SSCC labels, or talk to a WMS.
