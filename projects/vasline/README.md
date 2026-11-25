# VasLine

Value-added services workbench for a warehouse packing row.

VasLine is a pack-desk “will this shift clear?” planner. You describe the benches and the VAS jobs; it returns a bench chart, leftover work, and every tardy finish.

It is a planner, not a live WMS. Operation times are typical dock-side figures, not a particular labour standard.

## How it works

1. **Ops.** Each step is one of `relabel`, `kit`, `insert`, `wrap`, `inspect`, `shrink`, `ticket`, `rework`. A bench only takes steps whose skill it has. Omit `seconds_per_unit` / `setup_seconds` to use the catalog defaults (`python3 -m vasline ops`).
2. **Order.** Jobs sort **rush first** (priority 1 before 5), then **earliest due**, then job id. A listed bulk job does not keep a rush label job waiting.
3. **Place.** For each step, pick the skilled bench that can **finish earliest** (then bench id). Setup is paid when that bench’s last family is set and different. Setup starts as soon as the bench is free; work starts after setup **and** after the job’s previous step.
4. **Serial job, parallel benches.** Steps of one job never overlap. Two jobs on two benches can both start at `0:00`.
5. **Atomic leftover.** If any step cannot land before that bench’s shift ends, the **whole job** is leftover. Nothing sits half-kitted. Same if no bench has the skill.

### Workbook file

```json
{
  "benches": [
    {
      "id": "B1",
      "name": "Label bench",
      "skills": ["relabel", "ticket", "insert"],
      "shift_min": 480
    }
  ],
  "jobs": [
    {
      "id": "ORD-101",
      "sku": "STORE-TEE",
      "units": 40,
      "due_min": 60,
      "priority": 2,
      "family": "STORE",
      "steps": [{ "op": "relabel", "seconds_per_unit": 8, "setup_seconds": 90 }]
    }
  ]
}
```

Job and bench ids must be unique. `due_min` is minutes from shift start. Priority is 1 (rush) through 5. Family is the changeover group (store labels vs DTC labels, kit vs gift wrap).

### Operation catalog (short)

| Id | What | Default s/unit | Setup s |
| --- | --- | --- | --- |
| `relabel` | Store / GS1 labels | 8 | 90 |
| `kit` | Bundle components | 25 | 180 |
| `insert` | Coupon / manual | 6 | 60 |
| `wrap` | Gift wrap | 40 | 120 |
| `inspect` | QA pass | 12 | 45 |
| `shrink` | Heat-shrink | 15 | 150 |
| `ticket` | Hangtag | 5 | 75 |
| `rework` | Carton repair | 30 | 90 |

## How to run

Needs **Python 3.10+**. No pip packages.

From this project folder (the staged copy in the factory repo is `projects/vasline`):

```bash
# List operations and default times
PYTHONPATH=src python3 -m vasline ops

# Plan an example (human-readable bench chart)
PYTHONPATH=src python3 -m vasline plan examples/balanced-shift.json

# Same result as JSON
PYTHONPATH=src python3 -m vasline plan examples/skill-miss.json --json

# Local VAS desk
PYTHONPATH=src python3 -m vasline serve --host 127.0.0.1 --port 8797
```

Then open [http://127.0.0.1:8797](http://127.0.0.1:8797).

On the page:

1. Load `balanced-shift`, `changeover-hit`, `skill-miss`, `late-due`, or `priority-cut`, or edit benches and jobs.
2. Click **Plan shift**. Scheduled count, makespan, bench use, leftover / tardy, and the Gantt update together.

CLI exit codes: `0` every job staged, `2` at least one leftover, `1` usage or parse error. Tardy jobs still count as staged.

### Optional install

```bash
pip install -e .
vasline plan examples/balanced-shift.json
vasline serve
```

### Tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Coverage includes first-job origin, same-bench queue, cross-bench serial steps, family changeover, atomic leftover, shift overflow, rush cut-in, due-date order, parallel start, CLI exit codes, and the HTTP plan API.

## Examples

| File | What you should see |
| --- | --- |
| `examples/balanced-shift.json` | 5 jobs on 3 benches, makespan **16:05**, nothing leftover or tardy (exit 0) |
| `examples/changeover-hit.json` | STORE labels `0:00–5:20`, then **90 s setup**, DTC labels `6:50–12:10` |
| `examples/skill-miss.json` | Relabel stages; **gift wrap leftover** (no wrap skill) (exit 2) |
| `examples/late-due.json` | 30 min shift: RUSH-A **tardy** at 13:20 (due 10:00); BULK-B leftover |
| `examples/priority-cut.json` | RUSH-01 (priority 1) starts at **0:00** even though BIG-STORE is listed first |

## Limits

- Greedy list schedule: good for a pack-desk check, not a guaranteed optimal roster.
- One operator per bench, no preemption, no split lots.
- Labour standards, breaks, and multi-shift carry-over are out of scope.
