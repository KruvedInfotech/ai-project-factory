# TaskWeave

Forklift task-interleaving planner for a grocery DC, produce cold chain, store DC, or parcel inbound.

TaskWeave is a dispatch-desk “who takes the next pallet?” planner. You describe the floor and the task board; it pins each putaway, replen, pick, or relocate onto a truck, lists leftovers, and draws a local floor map plus a Gantt.

It is a planner, not a live WMS. Cell sizes and truck speeds are working figures, not a particular OEM spec sheet.

PickPath walks a pick wave. PutSteer seats inbound pallets. FaceFill fills pick faces. TaskWeave is the truck in between: after a putaway drop in aisle 3, grab a nearby outbound instead of deadheading empty to the dock.

## How it works

1. **Dispatch.** The planner repeatedly claims the best remaining (truck, task) pair. **Auto** takes hot tickets first (`priority` 1), then the shortest empty deadhead, then a dual-cycle bonus. **Fifo** walks ready time. **Nearest** leads with deadhead. **Dual** leads with the inbound↔outbound bonus so a putaway drop will grab a pick instead of another inbound.
2. **Claim a truck.** A dual-cycle bonus fires when the truck’s last leg was inbound (putaway/replen) and the candidate is outbound (pick), or the reverse. Nearest ignores that bonus.
3. **Accept a leg** only if all of these hold:
   - The truck kind can stand at both ends (`jack` is dock/staging only, `sitdown` may enter an aisle, `reach` may enter reserve)
   - Pallet height fits the mast and both location clearances
   - Pallet count and weight fit the truck
   - Temperature matches (`dry` / `chill` / `freeze`, unless the truck is `mixed`)
   - The task is ready before shift end
   - Deadhead + pickup + loaded travel + drop finishes before shift end
   - Those minutes still fit the labor cap
4. **Leftover.** Tasks that fail those checks keep a reason (`equipment`, `temp`, `too-tall`, `too-heavy`, `cube`, `too-late`, `shift`, `labor-cap`). Earlier legs are never pulled to help a later task.

Travel minutes are the ceiling of Manhattan cells ÷ `cells_per_min`. Already-there is free. Grocery default is **2 minutes** at pickup and again at drop. A board can override `labor_minutes`.

### Floor presets

| Id | What | Grid | Fleet | Shift | Labor |
| --- | --- | --- | --- | --- | --- |
| `grocery` | 6-aisle grocery DC | D1–D3 dock, S1–S2 staging, A1–A6 bays 1–6, R1–R2 reserve | RT-1, RT-2 reach; SD-1 sit-down | 480 min | 240 min |
| `produce` | 6-aisle produce cold chain | C1–C2 chill dock, F3 freeze, A1–A3 chill, A4–A6 freeze | RT-C chill reach, RT-F freeze reach | 360 min | 160 min |
| `dc` | 8-aisle store DC | D11–D14 dock, S11–S12 staging, A1–A8 | 3 reach, 2 sit-down | 600 min | 360 min |
| `parcel` | 4-door parcel inbound | P1–P2 dock, T1–T2 staging, A1 floor slots | JK-1, JK-2 pallet jack | 240 min | 80 min |

You can override labor, `shift_end_min`, or the `trucks` list on a preset, or pass a custom floor with `locations` and `trucks`.

### Board file

```json
{
  "floor": { "preset": "grocery" },
  "strategy": "auto",
  "labor_minutes": 240,
  "tasks": [
    {
      "id": "PUT-11",
      "kind": "putaway",
      "from": "D1",
      "to": "A3-3",
      "pallets": 1,
      "weight_kg": 420,
      "height_mm": 1400,
      "temp": "dry",
      "priority": 1,
      "ready_min": 0
    }
  ]
}
```

Each task id must be unique. `priority` 1 is hottest. Kind is `putaway`, `replen`, `pick`, or `relocate`. Temp is `dry`, `chill`, or `freeze`. Times are minutes from shift start.

## How to run

Needs **Python 3.10+**. No pip packages.

From this project folder (the staged copy in the factory repo is `projects/taskweave`):

```bash
# List warehouse floors
PYTHONPATH=src python3 -m taskweave presets

# Plan an example (human-readable table)
PYTHONPATH=src python3 -m taskweave weave examples/clear-board.json

# Same result as JSON
PYTHONPATH=src python3 -m taskweave weave examples/clear-board.json --json

# Force a strategy
PYTHONPATH=src python3 -m taskweave weave examples/dual-cycle.json --strategy nearest

# Local floor map
PYTHONPATH=src python3 -m taskweave serve --host 127.0.0.1 --port 8786
```

Then open [http://127.0.0.1:8786](http://127.0.0.1:8786).

On the page:

1. Pick a floor (default is grocery) and a labor cap.
2. Edit the task table, or load `clear-board`, `dual-cycle`, `equipment-block`, or `labor-capped`.
3. Click **Weave tasks**. Weaved count, dual cycles, deadhead %, leftovers, the floor map, and the Gantt update together.

CLI exit codes: `0` every task weaved, `2` at least one task left behind, `1` usage or parse error.

### Optional install

```bash
pip install -e .
taskweave weave examples/clear-board.json
taskweave serve
```

### Tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Coverage includes same-truck dual-cycle, two-truck parallel putaway, dual vs nearest after a drop, jack leftover on an aisle, freeze leftover on a chill truck, labor leftover, too-late, too-tall, too-heavy, cube, shift leftover, CLI exit codes, and the HTTP weave API.

## Examples

| File | What you should see |
| --- | --- |
| `examples/clear-board.json` | 4 grocery tasks, nothing left behind. RT-1 weaves `PUT-11` then `PICK-11`; RT-2 weaves `PUT-21` then `PICK-21` |
| `examples/dual-cycle.json` | One reach truck. Dual takes the far pick after `PUT-11`; nearest would have taken the closer replen |
| `examples/equipment-block.json` | Parcel jacks seat `PUT-40` dock→staging and leave aisle `PUT-41` as `equipment` |
| `examples/labor-capped.json` | 5-minute cap weaves `PUT-51` and leaves `PUT-52` as `labor-cap` |

## Limits

- Greedy planner: good for a fast dispatch check, not a guaranteed optimal tour.
- Trucks carry one task at a time. It does not batch two pallets onto a dual-fork unless they are already one task.
- It does not lock aisles, charge batteries, or talk to a WMS.
