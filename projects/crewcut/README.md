# CrewCut

Warehouse labor and shift staffing planner for a grocery DC, produce cold chain, store DC, or parcel inbound.

CrewCut is a time-office “who works this hour?” planner. You describe the site, the demand curve, and the roster; it seats associates onto hours, lists uncovered slots, and draws a local coverage chart plus a Gantt.

It is a planner, not a live WFM. Rates, headcounts, and break rules are working figures, not a particular labor contract.

WaveCut cuts orders into pick waves. TaskWeave dispatches forklifts. CrewCut is the roster in between: keep Rivera on the pick line, punch Temp-3 only when the in-window regular would go into overtime, and leave a freeze pick uncovered rather than seat a dry associate.

## How it works

1. **Expand.** A demand row with `heads: 2` becomes two tickets for that hour and skill.
2. **Order.** Hot tickets (`priority` 1) go first, then shift-hour order, then skill. Overnight sites walk 22:00 → 05:00, not 00:00 → 23:00.
3. **Claim a body.** The planner seats the best remaining associate on each ticket. **Auto** prefers an in-window person over overtime, then someone already on the clock, then a regular before a temp, then the least-flexible skill set. **Regular** leads with kind. **Temp** leads with temps (short spikes). **Overtime** leads with continuity so a picker already on the line extends into OT instead of opening a new punch.
4. **Accept a seat** only if all of these hold:
   - The associate has the skill
   - Forklift demand names an `equipment` the associate is certified for (`reach` / `jack` / `sitdown`)
   - Temperature matches (`dry` / `chill` / `freeze`, unless the associate is `mixed`)
   - The hour is inside availability, or it is overtime still inside `ot_cap_hours` (time-and-a-half)
   - It is not a mandatory break hour (default: after **4** consecutive hours)
   - A new punch still fits the head cap
   - The hour’s cost still fits the labor cap
5. **Leftover.** Tickets that fail those checks keep a reason (`skill`, `cert`, `temp`, `window`, `break`, `ot-cap`, `head-cap`, `labor-cap`, `no-body`). Earlier seats are never pulled to help a later hour.

A person works at most one ticket per clock hour. Overtime is any hour outside `available_start`–`available_end` (end exclusive), including coming in early.

### Site presets

| Id | What | Shift | Labor | Heads | Break |
| --- | --- | --- | --- | --- | --- |
| `grocery` | Grocery DC day | 06:00–14:00 | $1600 | 12 | 4 h |
| `produce` | Produce night cold chain | 22:00–06:00 | $1400 | 8 | 4 h |
| `dc` | Store DC | 05:00–15:00 | $2800 | 16 | 4 h |
| `parcel` | Parcel inbound | 08:00–16:00 | $900 | 8 | 4 h |

You can override `labor_dollars`, `head_cap`, or `break_after` on a preset, or pass a custom site with `shift_start`, `shift_end`, `labor_dollars`, and `head_cap`.

### Board file

```json
{
  "site": { "preset": "grocery" },
  "strategy": "auto",
  "labor_dollars": 1600,
  "demand": [
    {
      "hour": 8,
      "skill": "pick",
      "heads": 2,
      "temp": "dry",
      "priority": 1
    }
  ],
  "crew": [
    {
      "id": "A-12",
      "name": "Rivera",
      "kind": "regular",
      "skills": ["pick"],
      "rate_per_hour": 18,
      "available_start": 6,
      "available_end": 14,
      "ot_cap_hours": 2,
      "temp": "dry"
    }
  ]
}
```

Each associate id must be unique. `priority` 1 is hottest. Skill is `pick`, `pack`, `receive`, `replen`, or `forklift`. Temp is `dry`, `chill`, or `freeze` on demand (`mixed` is allowed on people). Forklift rows may set `equipment`. Hours are 0–23.

## How to run

Needs **Python 3.10+**. No pip packages.

From this project folder (the staged copy in the factory repo is `projects/crewcut`):

```bash
# List shift-site catalogs
PYTHONPATH=src python3 -m crewcut presets

# Plan an example (human-readable table)
PYTHONPATH=src python3 -m crewcut staff examples/clear-board.json

# Same result as JSON
PYTHONPATH=src python3 -m crewcut staff examples/clear-board.json --json

# Force a strategy
PYTHONPATH=src python3 -m crewcut staff examples/overtime.json --strategy overtime

# Local roster board
PYTHONPATH=src python3 -m crewcut serve --host 127.0.0.1 --port 8787
```

Then open [http://127.0.0.1:8787](http://127.0.0.1:8787).

On the page:

1. Pick a site (default is grocery) and a strategy.
2. Edit demand and crew, or load `clear-board`, `overtime`, `skill-block`, or `labor-capped`.
3. Click **Staff shift**. Covered count, fill %, labor $, leftovers, the coverage bars, and the Gantt update together.

CLI exit codes: `0` every demand slot seated, `2` at least one slot left behind, `1` usage or parse error.

### Optional install

```bash
pip install -e .
crewcut staff examples/clear-board.json
crewcut serve
```

### Tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Coverage includes two-head seating, continuity across hours, auto vs overtime vs temp vs regular, freeze leftover, reach-cert leftover, labor leftover, head-cap leftover, window leftover, OT-cap leftover, the four-hour break, overnight wrap, least-flexible skill use, CLI exit codes, and the HTTP staff API.

## Examples

| File | What you should see |
| --- | --- |
| `examples/clear-board.json` | 11 grocery slots, nothing left behind. Rivera and Chen pick; Patel packs; Ortiz takes receiving |
| `examples/overtime.json` | Auto seats Temp-3 in-window at 11:00; `--strategy overtime` keeps Rivera into OT instead |
| `examples/skill-block.json` | Produce night. Ng takes the chill pick; freeze pick leftover is `temp`; reach forklift leftover is `cert` |
| `examples/labor-capped.json` | $18 cap seats 08:00 and leaves 09:00 as `labor-cap` |

## Limits

- Greedy seater: good for a fast time-office check, not a guaranteed minimum-cost roster.
- Breaks are a consecutive-hour rule, not a full meal-period or union matrix.
- Factors such as punch rounding, shift differentials, and attendance are out of scope.
