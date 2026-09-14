# Task 13 — Rework Response

Verdict was APPROVE; all findings were minor/nit and all were integrated.
The branch was also rebased onto the reworked task-07 tip, which required
adapting one test (see integration note).

## Findings

- **m1 — accepted** (`5635fbf52`). Items 10 (synchrotron parameters) and 11
  (radiation plugin defaults) are now tracked: status-table rows
  (`open — deferred (optional trivial mirror, after the core items)`) and
  matching entries 5/6 in "Next PRs"; the body sentence that misdescribed
  where the deferral was recorded is corrected.
- **m2 — accepted** (`5635fbf52`). Pre-existing bug #2 is scoped to the
  collision setup only. `Simulation.customuserinput` (non-empty) and
  `Binning.openPMDBackendConfig` (set) render fine at the base commit and at
  this branch (reviewer-verified), so they are no longer listed as affected;
  the "Next PRs" reference was updated accordingly (#1/#2 -> #1).
- **n1 — accepted, cheapest option** (`4cc0a479d`). The class docstring and
  the two member tests now state explicitly that only C++ identifier-ness is
  checked, not the existence of the struct (pointing at the `Pusher.Axel`
  note in `species.py`); the two member tests were renamed to match.
- **n2 — accepted** (`4cc0a479d`). Both always-true self-identity asserts
  (`Pusher[x] is Pusher[x]`, `Shape[y] is Shape[y]`) deleted; the meaningful
  translation assertions remain.
- **n3 — accepted** (`5635fbf52`). The item-4 example now reads: electron
  mass ratio -> `0.99999999999656941` (the particle-package CODATA electron
  mass differs from the rounded C++ base by ~3.4e-12) and electron charge
  ratio -> `1.0` (both negative). Recomputed independently:
  `9.1093837138687491e-31 / 9.1093837139e-31 = 0.9999999999965694`,
  matching the reviewer's rendered battery evidence
  (`speciesDefinition.param`: `MassRatio 0.99999999999656941`,
  `ChargeRatio 1.0`).

## Integration note (rebase onto reworked task-07)

The branch was rebased onto the reworked task-07 tip. Task-07's
union-to-template exhaustiveness test landed on the 07 lineage after this
branch diverged, so it pinned the pre-reorganisation anchors. Two commits
adapt it to the reorg:
- `ed864c79e` — `SimpleDensity`/`{{#type_simpledensity}}` ->
  `CreateDensity`/`{{#type_createdensity}}` (the CreateDensity reorg already
  includes the deterministic species-order tie-break that task-07's
  SimpleDensity flake fix added, so the deleted file loses nothing).
- `0e84858ba` — `{{#layout.type_*}}` -> `{{#start_position.type_*}}`
  (the field/template rename from the reorg).

## Gates

- `pytest quick/ -q` -> **609 passed, 2 xfailed, 1 xpassed** (3512 subtests).
  The 566 baseline quoted in the review was measured on the pre-rework 07
  base; the rebased branch adds task-07's rework tests.
- `pre-commit run --all-files` -> exit 0, all hooks passed.
