# Response to Review - Task 11: LEXIS/EFP submission configuration

- **Branch:** `task-11-efp-lexis-config`, rework on top of review commit
  `debe38f73` (no history rewrites)
- **Rework commits:** `34331c960` (C1), `083a61836` (M1), `92b79fbae`
  (m2/m3/n1/n2 + M1 doc wording), `2bd1c3dda` (m1 + FINDINGS updates),
  `dc955fc32` (ruff format)

## Dispositions

| ID | Disposition | Commit |
|----|-------------|--------|
| C1 | **Fixed (matcher, not rename).** `_preset_path` keeps the legacy two-pass result for every selection it already made unique and only breaks ties by specificity (exact path > full preset dir > path prefix > queue/file prefix; bare substring is not a tie-breaker). The `efp-<system>` naming convention is kept per the task spec; a rename would defer the collision (e.g. `efp-gh200-jsc` contains `gh200`, which was a valid dev selection resolving to `jupiter-jsc`). | `34331c960` |
| M1 | **Fixed (code, not docs-only).** CWD/parent discovery now also matches the canonical `picongpurc.toml` (as the XDG and PIC_RC lookups already do), preserving per-directory (CWD first) and per-pattern (plain name first) priority; dotfile behaviour unchanged. Doc reworded to the precise route ("the directory you run the script from"). | `083a61836`, `92b79fbae` |
| m1 | **Fixed.** `TASK-11-FINDINGS.md` is ASCII (35 lines fixed); `TASK-*.md` added to the require-ascii exclusion because the committed `TASK-11-REVIEW.md` (85 non-ASCII lines) is a review-team artifact that the author must not modify - the review's suggested alternative. | `2bd1c3dda` |
| m2 | **Fixed.** Dropped the "after sourcing the profile" parenthetical (n1) and re-indented the following paragraph to the list-item indent; docutils "Unexpected indentation" gone. | `92b79fbae` |
| m3 | **Fixed.** Underline extended to the 42-char title length (the actual underline was 40 chars, not 38 as measured in the review). | `92b79fbae` |
| n1 | **Fixed.** Parenthetical removed; the explicit `-t` form in the code block already works without sourcing. | `92b79fbae` |
| n2 | **Fixed.** Configurability now states that `picongpu_run()`/CWL is not the EFP submission path (`run_submit_system` defaults to the profile's `TBG_SUBMIT=sbatch`). | `92b79fbae` |

All eight findings were independently verified at the review tip before
fixing (C1/M1 reproduced; pre-commit red on both `TASK-11-FINDINGS.md`
and `TASK-11-REVIEW.md`; both RST defects reproduced with docutils).
No findings rejected.

## C1 - before / after

Before (review tip `debe38f73`):

```
$ python -c "from picongpu._rc_params import RCParams; RCParams(preset='jupiter-jsc')"
ValueError: The given preset='jupiter-jsc' is ambiguous
  (candidates=['efp-jupiter-jsc/efp_picongpu.profile.example', 'jupiter-jsc/gh200_picongpu.profile.example']).
```

Same for `preset='jupiter'`, `'jup'`, ... (9 short forms; see sweep below).

After (`34331c960`):

```
preset=jupiter-jsc   -> etc/picongpu/jupiter-jsc/gh200.tpl   (preset_dir=jupiter-jsc)
preset=jupiter       -> etc/picongpu/jupiter-jsc/gh200.tpl
preset=jup           -> etc/picongpu/jupiter-jsc/gh200.tpl
preset=efp-jupiter-jsc -> etc/picongpu/efp-jupiter-jsc/gh200_efp.tpl
preset=efp           -> etc/picongpu/efp-jupiter-jsc/gh200_efp.tpl
```

**Sweep evidence** (1845 strings: all dir names, file names, stems, full
paths and all their prefixes, evaluated against the dev preset list and
the branch preset list, old matcher vs new `_preset_path`):

- **0** currently-valid dev selections change meaning (dev and branch).
- The **9** regressed short forms (`jup`, `jupi`, `jupit`, `jupite`,
  `jupiter`, `jupiter-`, `jupiter-j`, `jupiter-js`, `jupiter-jsc`)
  resolve to `jupiter-jsc` again - the review's regression count.
- 36 previously-ambiguous 1-2-char fragments (e.g. `A100`, `gpu.profile`,
  `le`) now resolve to the unique preset they prefix (error ->
  resolution; no selection that worked changes).
- Accepted delta, documented: the fragment `"ef"` (a valid dev selection
  only by accident - a substring of `de**f**q` in `hemera-hzdr/defq_...`)
  now resolves to the EFP preset, because it uniquely prefixes
  `efp-jupiter-jsc/...`. Any fix must either error or pick one for this
  fragment; the path-prefix tie-break is the same mechanism that
  disambiguates `jupiter`.

**Note on the review's suggested patch:** the proposed 2-line anchor
(`startswith(f"{preset}/")` as first pass, substring as fallback) does
not satisfy the review's own required regression test - with it,
`RCParams(preset="jupiter")` still matches both `jupiter-jsc/...` and
`efp-jupiter-jsc/...` via the substring fallback and raises
"ambiguous". The specificity tie-break covers path prefixes as well as
directory names.

New tests (`test_efp_preset.py::test_pre_existing_jupiter_preset_
selections_still_resolve`): `jupiter-jsc`/`jupiter`/`jup` pin the
jupiter-jsc preset, `efp`/`efp-jupiter-jsc` pin the EFP preset, and the
still-genuinely-ambiguous `jsc` raises.

## M1 - before / after

Before (review tip): `search_for_in_parents` used the glob
`[.]*picongpurc.toml`, which matches only dot-prefixed names:

```
$ python -c "from pathlib import Path; print(list(Path('.').glob('[.]*picongpurc.toml')))"  # cwd has picongpurc.toml
[]
```

Per the review's E2E repro, the PICMI script + `picongpurc.toml`
(`preset = "efp-jupiter-jsc"`) in one directory yielded
`rc_params.get("picongpurc_path") is None` and a 10-line fallback profile
(no module stack, no `TBG_*`, no `PIC_BACKEND`) - no error raised.

After (`083a61836`), the same reproduction:

```
$ python sim.py            # picongpurc.toml next to sim.py
DISCOVERED: /tmp/opencode/t11-m1-repro/picongpurc.toml
# setup/etc/picongpu/efp-jupiter-jsc/{efp_picongpu.profile.example,gh200_efp.tpl} present
# setup/workflow/scripts/picongpu.profile selects etc/picongpu/efp-jupiter-jsc/gh200_efp.tpl
```

New tests: 4 unit tests in `test_rc_params.py` (plain name in CWD,
dotfile still found, parent directory, same-directory priority) and an
E2E subprocess test in `test_efp_preset.py`
(`test_laptop_flow_discovers_rc_file_next_to_picmi_script`) running the
documented laptop route end-to-end.

## Final gate results (at final tip)

- `pytest quick/`: **187 passed, 2 xfailed, 1 xpassed** (baseline 181 +
  6 new tests: 1 C1 + 5 M1).
- `pre-commit run --all-files`: **all 21 hooks passed** (was red at the
  review tip).
- docutils on the four touched RST pages: no "Unexpected indentation",
  no "Title underline" messages; remaining messages are Sphinx-only
  directives/roles (unknown to bare docutils) and the two pre-existing
  missing-include warnings in `tbg.rst` that are on `dev` as well.
- Review's C1 and M1 reproductions: both pass after the fixes (above).
- `TASK-11-FINDINGS.md` updated where the fixes changed its claims
  (preset-naming note, section 6.5-6.8, new section 11).
