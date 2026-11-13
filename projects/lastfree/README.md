# LastFree

Last-free-day, demurrage, and detention clock for one ocean container.

LastFree is a clerk-side “when is LFD, and what will it cost if we miss it?” planner. You describe the free-time clock, the availability date, and optional gate-out / empty-return dates. It returns last free days, charge days, accrued vs projected dollars, and a day-by-day calendar.

It is a planner, not a line invoice. Presets are typical inner-clock shapes, not a particular terminal tariff.

## How it works

1. **Pick a clock.** A preset sets how many free days you get and whether those days are **business** (skip Saturday, Sunday, and listed holidays) or **calendar** (every date counts). Demurrage (terminal storage) and detention (equipment on the street) each have their own count and rate table.
2. **Count last free day.** Free time starts on `available_on` for demurrage, and on `gate_out_on` for detention. Last free day (LFD) is the last counted free day. **Pickup or return on LFD is still free.**
3. **Charge the days after LFD.** Charge days are dates of that clock’s type in `(LFD, stop]`. Demurrage stops on gate-out (or `as_of` if the box is still in the terminal). Detention stops on empty return (or `as_of` if it is still out).
4. **Apply tiers.** The first N charge days use one daily rate, later days use the next tier. 20' boxes use the preset’s 20' factor; 45' uses the 45' factor; 40' and 40' HC are 1.0.
5. **Accrued vs projected.** Accrued is through `as_of`. Projected uses gate-out and empty-return when those dates are set, so you can price a planned pickup.

### Free-time presets

| Id | What | Demurrage free | Detention free |
| --- | --- | --- | --- |
| `uswc_port` | US West Coast terminal | 4 business | 4 calendar |
| `use_port` | US East Coast terminal | 5 business | 5 calendar |
| `inland_ramp` | Inland rail ramp | 2 business | 3 calendar |
| `line_calendar` | Steamship line style | 7 calendar | 7 calendar |

Rates on `uswc_port` (40'): demurrage $285 then $400 after 5 charge days; detention $160 then $280 after 4. `use_port` is $195 then $340 after 4 on both clocks. Override free-day counts with `overrides` in the JSON.

### Job file

```json
{
  "container": "MSCU1234567",
  "preset": "uswc_port",
  "size": "40",
  "available_on": "2026-11-10",
  "as_of": "2026-11-12",
  "gate_out_on": "2026-11-19",
  "empty_return_on": "2026-11-25",
  "holidays": ["2026-11-11"]
}
```

Container id is 4 letters plus 6–7 digits. Size is `20`, `40`, `40HC`, or `45`. Dates are `YYYY-MM-DD`. Gate-out and empty return are optional; empty return requires gate-out.

## How to run

Needs **Python 3.10+**. No pip packages.

From this project folder (the staged copy in the factory repo is `projects/lastfree`):

```bash
# List free-time presets
PYTHONPATH=src python3 -m lastfree presets

# Run an example (human-readable calendar)
PYTHONPATH=src python3 -m lastfree clock examples/still-inside.json

# Same result as JSON
PYTHONPATH=src python3 -m lastfree clock examples/weekend-holiday.json --json

# Local last-free-day board
PYTHONPATH=src python3 -m lastfree serve --host 127.0.0.1 --port 8791
```

Then open [http://127.0.0.1:8791](http://127.0.0.1:8791).

On the page:

1. Pick a clock (default is US West Coast) and a size.
2. Enter available / as-of dates, optional gate-out and empty return, and holidays.
3. Load `still-inside`, `weekend-holiday`, or `gated-with-fees`.
4. Click **Run clock**. LFD dates, dollars, and the day cells update together.

CLI exit codes: `0` projected $0, `2` projected charges, `1` usage or parse error.

### Optional install

```bash
pip install -e .
lastfree clock examples/gated-with-fees.json
lastfree serve
```

### Tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Coverage includes business-day LFD (weekend and holiday skip), pickup on LFD is free, tiered rates, 20' factor, detention independent of demurrage, accrued vs projected, CLI exit codes, and the HTTP clock API.

## Examples

| File | What you should see |
| --- | --- |
| `examples/still-inside.json` | Available Tue 10 Nov, as-of Thu 12, USWC 4 business free → LFD Fri 13 Nov, $0 |
| `examples/weekend-holiday.json` | Veterans Day skipped; gate-out 19 Nov and empty 25 Nov → demurrage LFD Mon 16, 3+3 charge days |
| `examples/gated-with-fees.json` | East Coast 5/5, gate-out 12 Nov, empty 20 Nov → 4 demurrage days + 4 detention days, $1,560 |

## Limits

- Planner, not a tariff engine: weekend rules, “who starts the clock,” and per-terminal cut-off hours vary.
- One container per job. Chassis split, per diem vs detention naming, and dual-clock port/rail handoffs are out of scope.
- Holidays are whatever you list. The tool does not ship a government holiday calendar.
