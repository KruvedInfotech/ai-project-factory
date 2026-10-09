# LotDraw

FEFO/FIFO lot allocator for outbound warehouse orders.

LotDraw is a desk-side “which lot ships?” planner. You describe the policy, the open lots, and the orders; it returns an allocation list, leftover demand, leftover stock, plus a local lot board.

It is a planner, not a WMS. Shelf-life floors are typical working figures, not a particular customer contract. It does not pick a path and it does not pack a carton.

## How it works

1. **Open the clock.** `today` is the draw date. A lot whose expiry is on or before today is `expired` and is never allocated.
2. **Sort the order queue.** Priority 1 goes first, then earliest `ship_by`, then order id.
3. **Filter lots.** For each order, LotDraw keeps lots that:
   - Match the SKU
   - Still have quantity
   - Are not on hold (`quality`, `recall`, `damage`)
   - Have remaining life at `ship_by` of at least the floor (order `min_remaining_days`, else the policy default)
4. **Sort the eligible lots** by strategy:
   - **FEFO.** Earliest expiry, then earliest received.
   - **FIFO.** Earliest received, then earliest expiry.
   - **Fewest.** Largest remaining lot first so a line uses fewer lot numbers.
5. **Draw.** Take from the next lot until the order is filled. A no-split policy (or `max_lots_per_line: 1`) will only accept a single lot that covers the whole line. Otherwise the draw stops at `max_lots_per_line`.
6. **Leftovers.** Unfilled quantity is listed with a reason (`no-stock`, `on-hold`, `short-life`, `expired`, `no-split`, `lot-cap`, `short-qty`). Earlier draws are never unpacked to help a later order.

### Policy presets

| Id | What | Remaining life | Split | Max lots |
| --- | --- | --- | --- | --- |
| `grocery_dc` | Grocery DC | 7 days | yes | 4 |
| `pharma_vault` | Pharma vault | 90 days | yes | 2 |
| `cosmetics_fc` | Cosmetics FC | 30 days | no | 1 |
| `fresh_cold` | Fresh cold room | 3 days | yes | 6 |

You can override `min_remaining_days`, `allow_split`, or `max_lots_per_line` on a preset, or pass a custom policy with those fields.

### Wave file

```json
{
  "policy": { "preset": "grocery_dc" },
  "today": "2026-10-09",
  "strategy": "fefo",
  "orders": [
    {
      "id": "SO-1001",
      "sku": "MILK-1L",
      "qty": 40,
      "ship_by": "2026-10-10",
      "priority": 1
    }
  ],
  "lots": [
    {
      "id": "L-M1",
      "sku": "MILK-1L",
      "qty": 24,
      "expiry": "2026-10-20",
      "received": "2026-10-01",
      "location": "A-02-1"
    }
  ]
}
```

Each order id and lot id must be unique. Dates are `YYYY-MM-DD`. Hold is empty, `quality`, `recall`, or `damage`. An order may set `min_remaining_days` to raise the shelf-life floor above the policy.

## How to run

Needs **Python 3.10+**. No pip packages.

From this project folder (the staged copy in the factory repo is `projects/lotdraw`):

```bash
# List allocation policies
PYTHONPATH=src python3 -m lotdraw presets

# Draw an example (human-readable table)
PYTHONPATH=src python3 -m lotdraw draw examples/grocery-wave.json

# Same result as JSON
PYTHONPATH=src python3 -m lotdraw draw examples/grocery-wave.json --json

# Local lot board
PYTHONPATH=src python3 -m lotdraw serve --host 127.0.0.1 --port 8773
```

Then open [http://127.0.0.1:8773](http://127.0.0.1:8773).

On the page:

1. Pick a policy (default is the grocery DC) and a strategy.
2. Edit the order and lot tables, or load `grocery-wave`, `short-life`, `quality-hold`, or `no-split`.
3. Click **Draw lots**. Allocations, leftovers, and the SKU lot bars update together.

CLI exit codes: `0` every order filled, `2` at least one leftover, `1` usage or parse error.

### Optional install

```bash
pip install -e .
lotdraw draw examples/grocery-wave.json
lotdraw serve
```

### Tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Coverage includes FEFO vs FIFO vs fewest, remaining-life skip, quality holds, no-split, expired lots, CLI exit codes, and the HTTP draw API.

## Examples

| File | What you should see |
| --- | --- |
| `examples/grocery-wave.json` | 4 grocery orders, FEFO splits MILK across L-M1 then L-M2, nothing left behind |
| `examples/short-life.json` | SO-2001 skips the 12-day juice and takes L-J2; SO-2003 leftover `short-life` |
| `examples/quality-hold.json` | API-X leftover `on-hold`; VIT-C takes 8 of 10, leftover `short-qty` |
| `examples/no-split.json` | SERUM leftover `no-split`; CREAM fills from one lot |

## Limits

- Greedy allocator: good for a fast lot check, not a guaranteed optimal mix of lots.
- Remaining life is measured at `ship_by`, not at the customer’s door.
- One SKU per order line. Kits, catches, and catch-weight are out of scope.
- Factors such as serial capture, FEFO exceptions, and live WMS locks are out of scope.
