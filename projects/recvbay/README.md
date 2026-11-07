# RecvBay

Inbound receiving-bay planner for a dock.

RecvBay is a receiving-desk “where does this trailer sit?” planner. You describe the inbound doors and the ASNs; it pins each load to a door window, lists leftovers, and draws a local Gantt.

It is a planner, not a live WMS. Door equipment and shift lengths are working figures, not a particular warehouse drawing.

DockBook books the appointment. YardPark parks the trailer. RecvBay is the strip of time at the door: live vs drop, a leveler for floor-load, a reefer plug for chill, and a dwell that does not steal a window from a load already pinned.

## How it works

1. **Sort the board.** **Auto** takes hot tickets first (`priority` 1), then earliest ETA, then the biggest pallet count. **Eta** walks the clock. **Cluster** groups by vendor then temp. **Compact** docks the shortest unload first so more loads fit the shift.
2. **Claim a door.** Each ASN wants a free window. RecvBay prefers the booked door, then a door that already ran that vendor, then the earliest start. Drop trailers may wait for a door; live drivers may not.
3. **Accept a slot** only if all of these hold:
   - The door exists and matches the load temperature (`dry` / `chill` / `freeze`, unless the door is `mixed`)
   - Floor-loaded freight needs a dock leveler
   - Chill and freeze need a reefer plug
   - Trailer height fits the door
   - Pallet count fits the inbound staging pad
   - Booked door matches unless `mix_doors` is on
   - Vendor matches the door’s claim unless `mix_vendors` is on
   - Unload finishes before shift end
   - A live unload does not wait longer than `max_wait_min` after ETA
   - A live unload finishes within `appointment_min` of ETA
   - Unload minutes still fit the labor cap
4. **Leftover.** Loads that fail those checks keep a reason (`temp`, `equipment`, `too-tall`, `staging`, `vendor-mix`, `dwell`, `wait`, `door-busy`, `door`, `too-late`, `labor-cap`). Earlier slots are never pulled to help a later ASN.

Unload minutes are `pallets × minutes_per_pallet`. Floor-loaded trailers take **1.5×** that (ceiling). Grocery default is **8 minutes per pallet**. A board can override `labor_minutes`.

### Dock presets

| Id | What | Doors | Shift | Temp | Labor | Wait |
| --- | --- | --- | --- | --- | --- | --- |
| `grocery` | 6-door grocery inbound | D1–D4 dry, D5–D6 chill + reefer | 480 min | mixed | 240 min | 30 min |
| `produce` | 4-door produce inbound | C1–C2 chill, F3–F4 freeze | 360 min | cold | 160 min | 20 min |
| `dc` | 8-door store DC inbound | S11–S18 dry | 600 min | dry | 360 min | 45 min |
| `parcel` | 4-door parcel inbound | P1–P4 mixed, no leveler | 240 min | mixed | 80 min | 15 min |

You can override labor, `shift_end_min`, or `max_wait_min` on a preset, or pass a custom dock with a `doors` list (`id`, `number`, `temp`, `has_leveler`, `has_reefer`, `staging_pallets`, `height_mm`).

### Board file

```json
{
  "dock": { "preset": "grocery" },
  "strategy": "auto",
  "labor_minutes": 240,
  "mix_doors": false,
  "mix_vendors": true,
  "loads": [
    {
      "id": "ASN-11",
      "vendor": "NESTLE",
      "priority": 1,
      "temp": "dry",
      "pallets": 8,
      "unload": "live",
      "floor_loaded": false,
      "door": 1,
      "eta_min": 0,
      "appointment_min": 120
    }
  ]
}
```

Each load id must be unique. `priority` 1 is hottest. Temp is `dry`, `chill`, or `freeze`. Unload is `live` or `drop`. Vendor codes are uppercased. Times are minutes from shift start.

## How to run

Needs **Python 3.10+**. No pip packages.

From this project folder (the staged copy in the factory repo is `projects/recvbay`):

```bash
# List inbound docks
PYTHONPATH=src python3 -m recvbay presets

# Plan an example (human-readable table)
PYTHONPATH=src python3 -m recvbay dock examples/clear-dock.json

# Same result as JSON
PYTHONPATH=src python3 -m recvbay dock examples/clear-dock.json --json

# Force a strategy
PYTHONPATH=src python3 -m recvbay dock examples/dwell-block.json --strategy compact

# Local receiving Gantt
PYTHONPATH=src python3 -m recvbay serve --host 127.0.0.1 --port 8785
```

Then open [http://127.0.0.1:8785](http://127.0.0.1:8785).

On the page:

1. Pick a dock (default is grocery) and a labor cap.
2. Edit the ASN table, or load `clear-dock`, `floor-block`, `labor-capped`, or `dwell-block`.
3. Click **Plan dock**. Docked count, leftovers, labor, and the Gantt update together.

CLI exit codes: `0` every load docked, `2` at least one load left behind, `1` usage or parse error.

### Optional install

```bash
pip install -e .
recvbay dock examples/clear-dock.json
recvbay serve
```

### Tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Coverage includes same-door sequencing, live wait leftover, drop wait, vendor exclusive, door leftover, floor-load equipment, dwell leftover, labor leftover, too-late, too-tall, staging, door-busy, chill on dry, CLI exit codes, and the HTTP plan API.

## Examples

| File | What you should see |
| --- | --- |
| `examples/clear-dock.json` | 4 grocery ASNs, nothing left behind. ASN-11 and ASN-12 share door 1; SYSCO chill sits on D5 |
| `examples/floor-block.json` | Parcel dock seats palletized `ASN-40` and leaves floor-loaded `ASN-41` as `equipment` |
| `examples/labor-capped.json` | 64-minute cap docks `ASN-51` and leaves `ASN-52` as `labor-cap` |
| `examples/dwell-block.json` | 30-minute live window cannot cover an 8-pallet grocery unload → `ASN-60` leftover `dwell` |

## Limits

- Greedy planner: good for a fast receiving check, not a guaranteed optimal assignment.
- Doors are a snapshot. It does not free a bay when a trailer actually pulls.
- It does not print receiving labels, drive yard jockeys, or talk to a WMS.
