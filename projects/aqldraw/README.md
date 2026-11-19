# AqlDraw

Inbound AQL sampling desk for a receiving lot.

AqlDraw is a dock-side “how many cartons do I open, which ones, and at what defect count does the lot fail?” planner. You describe the receipt, inspection level, and lot sizes; it returns a sample-size letter, a deterministic carton draw, accept/reject numbers per defect class, and a switching hint for the next ASN.

It is a planner, not a live QMS. Tables are typical warehouse screening figures, not ISO 2859-1 or a supplier contract.

## How it works

1. **Letter.** Lot size N maps to a sample-size code letter on inspection **level II**. Level I slides one letter smaller, level III one letter larger. **S-2** is a spot-check band with a much smaller sample.
2. **Severity.** `reduced` / `normal` / `tightened` slides the same letter one more step. Tightened on a 500-unit lot is letter J (n = 80) instead of H (n = 50).
3. **Sample size.** Each letter has a planned n (A=2 … H=50 … Q=1250). If n ≥ N the whole lot is inspected (100%).
4. **Accept / reject.** For each defect class, λ = n × AQL / 100. Accept number is a Poisson 95% screen: `Ac = floor(λ + 1.645√λ)`. Reject is `Ac + 1`. AQL 0 is zero-tolerance (Ac = 0). Any class that fails fails the lot.
5. **Draw.** Carton numbers `1…N` are shuffled with a seed (`receipt|sku|letter|n`) and the first n are sorted so the inspector walks the aisle in order. Same seed, same draw.
6. **Switching (next receipt).** Screening, not ISO switching:
   - normal + 2 rejects in the last 5 lots → **tighten**
   - normal + 10 accepts in a row → **reduce**
   - tightened + 5 accepts in a row, or reduced + a reject → **return to normal**

Default classes: critical AQL 0.65, major 2.5, minor 6.5.

### Letters (level II, then cap at lot size)

| Lot size | Letter | n |
| --- | --- | --- |
| 2–8 | A | 2 |
| 9–15 | B | 3 |
| 16–25 | C | 5 |
| 26–50 | D | 8 |
| 51–90 | E | 13 |
| 91–150 | F | 20 |
| 151–280 | G | 32 |
| 281–500 | H | 50 |
| 501–1200 | J | 80 |
| 1201–3200 | K | 125 |
| 3201–10000 | L | 200 |
| 10001–35000 | M | 315 |

Skip I and O, same as common QC letter cards. S-2 uses coarser bands (2–25→A, 26–90→B, 91–500→C, 501–3200→D, …).

### Receipt file

```json
{
  "receipt": "ASN-4418",
  "supplier": "Northline Cartons",
  "dock": "Bay 4",
  "level": "II",
  "severity": "normal",
  "seed": "ASN-4418",
  "classes": {
    "critical": 0.65,
    "major": 2.5,
    "minor": 6.5
  },
  "history": ["accept", "accept", "accept", "accept", "accept"],
  "lots": [
    {
      "sku": "CARTON-A",
      "description": "12-pack bottles",
      "lot_size": 500,
      "found": { "critical": 0, "major": 1, "minor": 3 }
    }
  ]
}
```

Each SKU must be unique. `found` is optional — omit it to print the draw and wait for the inspector. `history` is prior receipt verdicts, newest last. Datetimes are not used; this is a count-based screen.

## How to run

Needs **Python 3.10+**. No pip packages.

From this project folder (the staged copy in the factory repo is `projects/aqldraw`):

```bash
# List levels, letters, and AQL presets
PYTHONPATH=src python3 -m aqldraw cards

# Draw an example (human-readable board)
PYTHONPATH=src python3 -m aqldraw draw examples/inbound-pass.json

# Same result as JSON
PYTHONPATH=src python3 -m aqldraw draw examples/inbound-reject.json --json

# Local QC desk
PYTHONPATH=src python3 -m aqldraw serve --host 127.0.0.1 --port 8794
```

Then open [http://127.0.0.1:8794](http://127.0.0.1:8794).

On the page:

1. Load `inbound-pass`, `inbound-reject`, `small-lot`, or `switch-tighten`, or edit the lot table.
2. Set level, severity, and the three AQL percents.
3. Click **Draw sample**. Receipt verdict, carton map (brass = open this one), accept/reject numbers, and switching advice update together.

CLI exit codes: `0` no lot rejected (accept or still pending), `2` at least one lot rejected, `1` usage or parse error.

### Optional install

```bash
pip install -e .
aqldraw draw examples/inbound-pass.json
aqldraw serve
```

### Tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Coverage includes letter bands and level/severity slides, Poisson Ac screens, 100% cap, stable carton draws, inbound pass/reject examples, small-lot critical fail, 2-of-5 tighten advice, CLI exit codes, and the HTTP draw API.

## Examples

| File | What you should see |
| --- | --- |
| `examples/inbound-pass.json` | 500 + 90 units, level II → letters **H / E** (n = 50 / 13); found 0/1/3 and 0/0/1 → **accept**; switching stay |
| `examples/inbound-reject.json` | 500 units, 4 major vs Ac 3 → **reject** (exit 2) |
| `examples/small-lot.json` | 12 kits, letter **B**, n = 3; one critical vs Ac 0 → **reject** |
| `examples/switch-tighten.json` | Prior reject + this reject = 2 of last 5 → switching **tighten** |

## Limits

- Screening cards, not ISO 2859-1 / ANSI Z1.4: letters, n, and Ac/Re will not match a paid standard book.
- Single sampling only (Re = Ac + 1). Double sampling, skip-lot, and C=0 plans are out of scope.
- Switching is a dock hint for the *next* ASN; it does not auto-change this draw.
- One receipt, unique SKUs, counts only. Attribute vs variable inspection, AQL by unit vs by carton, and lab metrology are out of scope.
