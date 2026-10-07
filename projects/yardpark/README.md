# YardPark

Yard trailer parking and pull-to-door sequencer.

YardPark is a desk-side “where does this trailer sit?” planner. You describe the yard spots and the trailers; it returns a parking map, leftover units, a hostler pull sequence, plus a local yard board.

It is a planner, not a YMS. Spot counts and clocks are typical working figures, not a particular site configuration. It does not book dock-door appointments and it does not match inbound freight to outbound orders.

## How it works

1. **Open the clock.** A trailer that arrives before yard open is available at open. Freight that arrives at or after close is leftover (`closed`).
2. **Sort the trailer queue.** Priority 1 goes first unless the strategy says otherwise:
   - **Auto.** Priority, then appointment, then longest dwell, then ETA.
   - **Door.** Units that already have a door, then appointment.
   - **Dwell.** Longest already-on-yard sit first — clear the aging trailers.
   - **Pull.** Outbound units with an appointment first so the hostler wave has somewhere to start.
3. **Claim a spot.** For each trailer, YardPark takes the free stall that fits:
   - Length must fit (`max_ft` on the stall)
   - Reefer freight needs a reefer or power stall
   - `needs_power` also needs a plug (reefer or power)
   - A stall whose nearest door matches the trailer’s door wins
   - Outbound prefers a short walk
   - Dry freight without a plug avoids reefer and power stalls so those stay free
4. **Sequence pulls.** Parked trailers that have a door *and* an appointment (and are not empties) enter the hostler list, soonest appointment first. A pull starts at the later of “available”, “previous pull finished”, and “appointment minus pull lead”. Ready time is start plus hook time plus walk, plus a row-change when the hostler hops rows.
5. **Accept a pull** only if all of these hold:
   - Ready time is at or before the appointment and yard close
   - Adding the move does not exceed max moves
   - Adding the move does not exceed the labor cap
6. **Leftovers and holds.** Units that cannot park are leftover (`no-spot`, `no-reefer`, `no-power`, `too-long`, `closed`). Parked units that never pull are held (`idle` for empties or no appointment, `capped` when labor is gone, `late` when the clock already missed the door). The process is greedy: an earlier park or pull is never unpacked.

### Yard presets

| Id | What | Hours | Spots | Moves | Labor |
| --- | --- | --- | --- | --- | --- |
| `mini_6` | Small demo yard | 08:00–16:00 | 4 dry + 2 reefer | 6 | 45 min |
| `metro_10` | City DC | 07:00–19:00 | 7 dry (1 pup) + 2 reefer + 1 power | 10 | 120 min |
| `dc_20` | Regional DC | 05:00–22:00 | 13 dry + 5 reefer + 2 power | 18 | 240 min |
| `cold_8` | Cold campus | 04:00–20:00 | 6 reefer + 2 power | 8 | 150 min |

You can override `open`, `close`, `minutes_per_move`, `row_change_min`, `pull_lead_min`, `max_moves`, or `max_labor_min` on a preset, or pass a custom yard with those fields plus `spots`.

### Yard-plan file

```json
{
  "yard": { "preset": "mini_6" },
  "strategy": "door",
  "trailers": [
    {
      "id": "IN-101",
      "kind": "inbound",
      "temp": "dry",
      "length_ft": 53,
      "eta": "08:15",
      "door": "D1",
      "dwell_h": 0,
      "priority": 1,
      "appointment": "09:00"
    }
  ]
}
```

Each trailer id must be unique. Times are `HH:MM`. Kind is `inbound`, `outbound`, or `empty`. Temperature is `dry` or `reefer`.

## How to run

Needs **Python 3.10+**. No pip packages.

From this project folder (the staged copy in the factory repo is `projects/yardpark`):

```bash
# List yard presets
PYTHONPATH=src python3 -m yardpark presets

# Park an example (human-readable table)
PYTHONPATH=src python3 -m yardpark park examples/inbound-wave.json

# Same result as JSON
PYTHONPATH=src python3 -m yardpark park examples/inbound-wave.json --json

# Local yard board
PYTHONPATH=src python3 -m yardpark serve --host 127.0.0.1 --port 8772
```

Then open [http://127.0.0.1:8772](http://127.0.0.1:8772).

On the page:

1. Pick a yard (default is the regional DC) and a labor cap.
2. Edit the trailer table, or load `inbound-wave`, `door-adjacent`, `reefer-short`, or `labor-capped`.
3. Click **Park yard**. Occupied stalls, pull sequence, leftovers, and labor update together.

CLI exit codes: `0` everything parked, `2` at least one leftover, `1` usage or parse error.

### Optional install

```bash
pip install -e .
yardpark park examples/door-adjacent.json
yardpark serve
```

### Tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Coverage includes door-adjacent parking, reefer and power rules, pup-length stalls, FIFO labor and late pulls, strategy order, CLI exit codes, and the HTTP park API.

## Examples

| File | What you should see |
| --- | --- |
| `examples/inbound-wave.json` | 7 trailers on the regional DC, 6 pulls, empty parked idle, nothing left behind |
| `examples/door-adjacent.json` | IN-101 on Y1-1 (D1), OUT-220 on Y2-1 (D2), both pulled |
| `examples/reefer-short.json` | Two reefers take Y3, third leftover `no-spot` |
| `examples/labor-capped.json` | Four outbound dry units park; a 14-minute cap leaves later pulls `capped` |

## Limits

- Greedy parker: good for a fast yard check, not a guaranteed optimal assignment.
- One trailer per stall. Drop-hook and dual-trailer spots are out of scope.
- No door time-slots and no inbound-to-outbound freight matching — those are different planners.
- Factors such as seal checks, chassis pools, and live hostler GPS are out of scope.
