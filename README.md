# AI Project Factory

Catalog and home base for scheduled AI mini-projects from [Kruved Infotech](https://kruvedinfotech.com/).

This repository is an index, not a monorepo of apps. Each mini-project is a **standalone GitHub repository** (default branch `main`). This catalog records what shipped, where the code lives, and how to run it.

## How the factory works

1. A scheduled Cursor automation runs on a regular cadence.
2. It picks a new, useful topic (not a repeat of something already published).
3. It builds one complete mini-project: source, tests, and a README that explains **how it works** and **how to run it**.
4. That project is published as **its own GitHub repo** under `KruvedInfotech`, on `main`, with commits authored as [chetanselukar07](https://github.com/chetanselukar07).
5. This catalog gets a new row: repo link, one-line description, clone command, and run command.

Until the dedicated GitHub repo exists, the full project is staged here under `projects/<slug>/` so it can be pushed as-is:

```bash
# Create the empty GitHub repo first, then from this factory checkout:
git subtree split --prefix=projects/<slug> -b <slug>
git push git@github.com:KruvedInfotech/<slug>.git <slug>:main
```

The GitHub App used by the automation can push to this factory repo. It cannot create new organization repositories, so someone with org access needs to create the empty project repo once.

## How to run a published project

```bash
git clone https://github.com/KruvedInfotech/<project>.git
cd <project>
# Follow that repo's README. For a staged project still in this catalog:
cd projects/<project>
```

Each project README is the source of truth for install, CLI, UI, tests, and limits. Python mini-projects here target Python 3.10+ and avoid extra packages unless the README says otherwise.

## Published projects

### LoadFit — logistics carton packer

| | |
| --- | --- |
| **Date** | 2026-09-07 |
| **Intended repo** | `https://github.com/KruvedInfotech/loadfit` (create this repo, then publish from the staged folder) |
| **Staged source** | [`projects/loadfit`](projects/loadfit/) |
| **What it is** | 3D packer for vans, trucks, and containers. Overlap-free placement, payload cap, isometric load map. |

**How it works (short):** cartons are expanded to individual pieces, largest first. LoadFit tries the lowest-back-left corner that stays inside the cargo box, does not overlap, and has a floor (the deck, or ≥70% support from cartons below). It can rotate on the floor (keep this side up) and stops when payload is full.

**How to run (from the staged folder):**

```bash
cd projects/loadfit
PYTHONPATH=src python3 -m loadfit presets
PYTHONPATH=src python3 -m loadfit pack examples/mixed-cartons.json
PYTHONPATH=src python3 -m loadfit serve --host 127.0.0.1 --port 8765
```

Open `http://127.0.0.1:8765`, then **Pack load**. Full detail is in the [LoadFit README](projects/loadfit/README.md).

### AqlDraw — inbound AQL sampling desk

| | |
| --- | --- |
| **Date** | 2026-11-19 |
| **Intended repo** | `https://github.com/KruvedInfotech/aqldraw` (create this repo, then publish from the staged folder) |
| **Staged source** | [`projects/aqldraw`](projects/aqldraw/) |
| **What it is** | Receiving QC desk. Sample-size letter, which cartons to open, accept/reject per defect class, switching hint. |

**How it works (short):** lot size maps to a letter (level and tightness slide it). Sample n follows the letter, capped at the lot. Accept number is a Poisson 95% screen on n × AQL / 100; any class that fails fails the lot. Carton numbers are a seeded shuffle, then sorted. Two rejects in five lots recommends tightening next time.

**How to run (from the staged folder):**

```bash
cd projects/aqldraw
PYTHONPATH=src python3 -m aqldraw cards
PYTHONPATH=src python3 -m aqldraw draw examples/inbound-pass.json
PYTHONPATH=src python3 -m aqldraw serve --host 127.0.0.1 --port 8794
```

Open `http://127.0.0.1:8794`, then **Draw sample**. Full detail is in the [AqlDraw README](projects/aqldraw/README.md).
