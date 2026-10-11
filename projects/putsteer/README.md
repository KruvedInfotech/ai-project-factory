# PutSteer

Directed putaway planner for inbound warehouse pallets.

PutSteer is a desk-side “where does this LPN go?” planner. You describe the policy, the inbound pallets, and the open locations; it returns a put list, leftover pallets, leftover slot capacity, plus a local rack map.

It is a planner, not a WMS. Height, weight, and labor figures are typical working numbers, not a particular site configuration. It does not redesign slotting and it does not refill a pick face from reserve.

## How it works

1. **Sort the inbound queue.** Priority 1 goes first, then heaviest. **Heavy** leads with weight, **tall** with height, **FIFO** with LPN id.
2. **Filter locations.** For each pallet, PutSteer keeps a slot that:
   - Is not blocked
   - Matches the policy location type (`reserve`, `pick`, or either)
   - Matches temperature (`dry` / `cool` / `frozen`)
   - Has height clearance
   - Has remaining pallet slots and remaining weight
   - Is empty, already holds the same SKU, or allows mixed SKUs
3. **Score the legal slots.** Same-SKU top-off wins when the policy asks for it. After that, a slot in the SKU velocity zone and near `home_aisle` (the pick-face aisle) beats a far empty hole. Floor levels beat upper racks; tight leftover capacity is preferred so honeycomb stays low.
4. **Claim.** The pallet occupies the winning slot. Travel is `minutes_per_put + aisle_change_min × |aisle − last aisle|` (receiving is aisle 0). When the next put would blow the labor cap, the rest of the queue is leftover.
5. **Leftovers.** Unplaced pallets are listed with a reason (`mix-sku`, `weight`, `height`, `no-space`, `blocked`, `type`, `temp`, `labor-cap`). Earlier puts are never unpacked to help a later LPN.

### Policy presets

| Id | What | Type | Mix SKU | Top-off | Labor |
| --- | --- | --- | --- | --- | --- |
| `reserve_dc` | Reserve DC | reserve | no | yes | 4 min + 2/aisle, 40 min |
| `pick_fc` | Forward pick FC | pick | no | yes | 3 min + 1/aisle, 24 min |
| `cold_vault` | Cold vault | any | no | yes | 5 min + 2/aisle, 16 min |
| `bulk_floor` | Bulk floor | reserve | yes | no | 6 min + 3/aisle, 60 min |

You can override `allow_mix_sku`, `prefer_topoff`, `location_type`, `minutes_per_put`, `aisle_change_min`, or `max_labor_min` on a preset, or pass a custom policy with those fields. A wave may also set `labor_minutes` to cap the clock without changing the preset.

### Wave file

```json
{
  "policy": { "preset": "reserve_dc" },
  "strategy": "priority",
  "inbound": [
    {
      "id": "LPN-1001",
      "sku": "RICE-10KG",
      "qty": 48,
      "height_mm": 1400,
      "weight_kg": 520,
      "temp": "dry",
      "velocity": "A",
      "priority": 1,
      "home_aisle": 1
    }
  ],
  "locations": [
    {
      "id": "R-A-01-1",
      "zone": "A",
      "type": "reserve",
      "aisle": 1,
      "bay": 1,
      "level": 1,
      "temp": "dry",
      "max_pallets": 2,
      "max_height_mm": 1800,
      "max_weight_kg": 1200
    }
  ]
}
```

Each pallet id and location id must be unique. Temperature is `dry`, `cool`, or `frozen`. Velocity and zone are `A`, `B`, or `C`. `pallets` is the number of slot positions the LPN occupies (default 1).

## How to run

Needs **Python 3.10+**. No pip packages.

From this project folder (the staged copy in the factory repo is `projects/putsteer`):

```bash
# List putaway policies
PYTHONPATH=src python3 -m putsteer presets

# Put an example (human-readable table)
PYTHONPATH=src python3 -m putsteer put examples/inbound-wave.json

# Same result as JSON
PYTHONPATH=src python3 -m putsteer put examples/inbound-wave.json --json

# Local rack map
PYTHONPATH=src python3 -m putsteer serve --host 127.0.0.1 --port 8774
```

Then open [http://127.0.0.1:8774](http://127.0.0.1:8774).

On the page:

1. Pick a policy (default is the reserve DC) and a strategy.
2. Edit the pallet and location tables, or load `inbound-wave`, `height-cap`, `cold-mismatch`, or `labor-capped`.
3. Click **Steer puts**. Assignments, leftovers, and the aisle rack map update together.

CLI exit codes: `0` every pallet put away, `2` at least one leftover, `1` usage or parse error.

### Optional install

```bash
pip install -e .
putsteer put examples/inbound-wave.json
putsteer serve
```

### Tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Coverage includes same-SKU top-off, height leftover, temperature mismatch, mix-SKU, labor cap, pick-vs-reserve type filter, heavy-first strategy, CLI exit codes, and the HTTP put API.

## Examples

| File | What you should see |
| --- | --- |
| `examples/inbound-wave.json` | 4 dry pallets into a reserve DC. Both RICE LPNs top off `R-A-01-1`; OIL and SOAP take their zone aisles. Nothing left behind. |
| `examples/height-cap.json` | TOWER-BIN leftover `height`; FLAT-CASE parks in the 1500 mm slot |
| `examples/cold-mismatch.json` | PEAS-FZN leftover `temp`; YOG-CUP takes the cool slot |
| `examples/labor-capped.json` | Two puts fill an 8-minute clock; the other two leftover `labor-cap` |

## Limits

- Greedy assigner: good for a fast receiving desk check, not a guaranteed optimal putaway.
- Slots are pallet-count and weight, not a full 3D cube (no nesting, no reach-truck envelope).
- Task interleaving, license-plate splits, and live WMS reservations are out of scope.
