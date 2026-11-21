# AllocPush

DC-to-store push allocator for a replenishment wave.

AllocPush is a desk-side “who gets the next case?” planner. You describe DC on-hand, store books, and case packs; it returns a push list, leftover at the DC, and who is still short.

It is a planner, not a live allocation or replenishment system. Grades and policies are typical retail screening rules, not a particular chain’s playbook.

## How it works

1. **Need.** For each store × SKU, target = `min(max_cap, max(min_face, forecast))`. Need = `max(0, target − on_hand)`. Presentation minimum can lift a weak forecast; capacity clips it.
2. **Pack.** Need is rounded **up** to whole packs so the store is covered, then clipped so on-hand + push never crosses `max_cap` in whole packs. Default pack is `case_pack`. `break_case` switches to `inner_pack`.
3. **Holdback.** `holdback_pct` of DC on-hand stays put (e-comm, later waves). Only the rest can ship, still in whole packs.
4. **Fill when the DC is long.** Every store gets its need packs. Extra units stay at the DC.
5. **Fill when the DC is short.** Policy decides:
   - **fair_share** (default) — Hamilton / largest remainder. Each store’s weight is `need_packs × grade` (A=3, B=2, C=1). Floor of `available × weight / total_weight`, cap at need, leftover packs to the largest remainders (then A before B before C, then store id).
   - **need_fill** — hungriest store first (then grade, then store id), fill each completely until the DC is empty.
   - **grade_first** — fill every A store, then B, then C.
6. **Short.** `short_units = max(0, need_units − push_units)`. Case-pack overage (shipping 24 to cover 13) counts as filled.

### Wave file

```json
{
  "wave": "WAVE-18",
  "dc": "DC-North",
  "policy": "fair_share",
  "holdback_pct": 0,
  "break_case": false,
  "skus": [
    {
      "sku": "TEE-NAVY",
      "description": "Navy crew tee",
      "case_pack": 12,
      "inner_pack": 6,
      "dc_on_hand": 480
    }
  ],
  "stores": [
    {
      "store_id": "ST-01",
      "name": "Downtown",
      "grade": "A",
      "books": [
        {
          "sku": "TEE-NAVY",
          "on_hand": 24,
          "forecast": 96,
          "min_face": 24,
          "max_cap": 180
        }
      ]
    }
  ]
}
```

SKU ids and store ids must be unique. A store with no book for a SKU is skipped on that SKU. Units are eaches.

## How to run

Needs **Python 3.10+**. No pip packages.

From this project folder (the staged copy in the factory repo is `projects/allocpush`):

```bash
# List policies and grade weights
PYTHONPATH=src python3 -m allocpush policies

# Allocate an example (human-readable board)
PYTHONPATH=src python3 -m allocpush push examples/balanced-push.json

# Same result as JSON
PYTHONPATH=src python3 -m allocpush push examples/short-stock.json --json

# Local allocation desk
PYTHONPATH=src python3 -m allocpush serve --host 127.0.0.1 --port 8795
```

Then open [http://127.0.0.1:8795](http://127.0.0.1:8795).

On the page:

1. Load `balanced-push`, `short-stock`, `grade-first`, or `holdback`, or edit the SKU and store-book tables.
2. Set policy, holdback percent, and whether to break cases.
3. Click **Push wave**. Fill %, DC leftover, store bars (amber = shipped, rust = still short), and per-store cards update together.

CLI exit codes: `0` every need filled, `2` at least one store still short, `1` usage or parse error.

### Optional install

```bash
pip install -e .
allocpush push examples/balanced-push.json
allocpush serve
```

### Tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Coverage includes balanced fill, Hamilton fair-share leftovers, grade-first vs need-fill on the same short wave, holdback, case rounding vs capacity, inner-pack break, min-face lift, CLI exit codes, and the HTTP push API.

## Examples

| File | What you should see |
| --- | --- |
| `examples/balanced-push.json` | TEE-NAVY 11 cases + HOOD-GRY 4 cases, DC long → **all filled** (exit 0) |
| `examples/short-stock.json` | 10 cases vs 22 needed; fair share → ST-01 **4**, ST-04 **2**, ST-09 **1**, ST-12 **3** (exit 2) |
| `examples/grade-first.json` | Same short wave, A stores first → ST-01 **8**, ST-12 **2**, Mall and Suburb **0** |
| `examples/holdback.json` | 20% of 240 stays at DC (48); 8 cases of socks cover every store |

## Limits

- One wave, unique SKUs, unique stores. No multi-DC, no in-transit, no store transfers.
- Pack rounding is greedy (up to cover need, then cap). It will not split a case across stores unless `break_case` is on.
- Fair share is count-based Hamilton, not a service-level or days-of-supply optimizer.
- Cube, weight, trailer routing, and pick-wave construction are out of scope.
