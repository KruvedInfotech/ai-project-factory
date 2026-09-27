# DockBook

Dock-door appointment booker for a warehouse yard.

DockBook is a gate-house “will it dock today?” planner. You describe the yard (doors, hours, turnaround) and the trailers; it returns a door assignment, leftover vehicles, fill per door, plus a local Gantt board.

It is a planner, not a WMS or YMS. Door capabilities are typical working rules, not a particular OEM dock spec.

## How it works

1. **Map the yard.** Each door lists the directions it accepts (`inbound` / `outbound`), the temperatures it accepts (`dry` / `reefer`), and a max trailer length.
2. **Sort the queue.** Priority 1 goes first. Ties go to the tightest appointment window, then the earliest window start.
3. **Find a slot.** For every remaining trailer, DockBook walks matching doors and looks for the earliest start that:
   - stays inside the trailer’s window
   - stays inside yard open/close
   - does not overlap a booking already on that door
   - leaves the configured **turnaround** gap after the previous trailer
4. **Pick a door** using the strategy:
   - **Earliest.** Soonest feasible start; door id breaks ties.
   - **Preferred.** Use `prefer_door` only. If that door cannot take the trailer, it is left in the yard.
   - **Spread.** Prefer the matching door with the fewest minutes already booked.
   - **Auto.** Honor `prefer_door` when it is feasible, otherwise behave like earliest.
5. **Leftovers.** A trailer that has no capable door, is longer than every door, or has no gap left in its window is listed with a reason. The process is greedy: an earlier booking is never unpacked to make a later one fit.

### Yard presets

| Id | What | Hours | Doors | Turnaround |
| --- | --- | --- | --- | --- |
| `fmcg_4` | Typical FMCG DC | 06:00–20:00 | 2 inbound dry, 1 outbound dry, 1 mixed/reefer | 15 min |
| `cold_3` | Cold store | 05:00–18:00 | 3 reefer (C3 is 12 m) | 20 min |
| `crossdock_8` | Cross-dock | 00:00–24:00 | 3 in / 3 out / 2 flex | 10 min |
| `mini_2` | Small demo yard | 08:00–16:00 | A mixed, B dry-only | 10 min |

You can override `open`, `close`, and `turnaround_min` on a preset, or pass a custom yard with `doors`.

### Day-plan file

```json
{
  "yard": { "preset": "fmcg_4" },
  "strategy": "auto",
  "trailers": [
    {
      "id": "IN-104",
      "carrier": "BlueLine",
      "direction": "inbound",
      "reefer": false,
      "length_m": 13.6,
      "duration_min": 75,
      "window_start": "07:00",
      "window_end": "11:00",
      "prefer_door": "D1",
      "priority": 1
    }
  ]
}
```

Each trailer id must be unique. Times are `HH:MM` on a single working day (`24:00` is allowed as yard close). Priority `1` is first in line.

## How to run

Needs **Python 3.10+**. No pip packages.

From this project folder (the staged copy in the factory repo is `projects/dockbook`):

```bash
# List yard presets
PYTHONPATH=src python3 -m dockbook presets

# Book an example (human-readable board)
PYTHONPATH=src python3 -m dockbook book examples/morning-inbound.json

# Same result as JSON
PYTHONPATH=src python3 -m dockbook book examples/morning-inbound.json --json

# Force a strategy
PYTHONPATH=src python3 -m dockbook book examples/morning-inbound.json --strategy spread

# Local door board
PYTHONPATH=src python3 -m dockbook serve --host 127.0.0.1 --port 8767
```

Then open [http://127.0.0.1:8767](http://127.0.0.1:8767).

On the page:

1. Pick a yard (default is the 4-door FMCG DC) and a strategy.
2. Edit the trailer table, or load `morning-inbound`, `reefer-overflow`, `outbound-cluster`, or `missed-window`.
3. Click **Book dock**. Booked count, door fill, leftovers, and the Gantt board update together.

CLI exit codes: `0` every trailer booked, `2` at least one left in the yard, `1` usage or parse error.

### Optional install

```bash
pip install -e .
dockbook book examples/outbound-cluster.json
dockbook serve
```

### Tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Coverage includes first-door placement, turnaround gaps, reefer/dry matching, overlength leftovers, preferred-door refusal, spread across doors, overlap checks, CLI exit codes, and the HTTP book API.

## Examples

| File | What you should see |
| --- | --- |
| `examples/morning-inbound.json` | 7 trailers into the FMCG yard, including a reefer on D4; nothing left behind |
| `examples/reefer-overflow.json` | Cold store: 3 reefers book, `RF-D` misses the morning gap, `DRY-1` has no dry door |
| `examples/outbound-cluster.json` | 4 outbound + 2 inbound on the 8-door cross-dock, spread across doors |
| `examples/missed-window.json` | `KEEP-A` / `KEEP-B` book; `LATE` overruns close; `LONG-HAUL` is too long |

## Limits

- One working day. No multi-day dwell, no live ETA tracking.
- Greedy assignment: good for a fast gate check, not a guaranteed optimal mix.
- No labour, forklift, or staging-lane constraints.
- Turnaround is a flat gap after each booking, not a measured dock-clear standard.
