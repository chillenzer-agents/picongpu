# Review — Task 11: LEXIS/EFP submission configuration (draft)

- **Branch:** `task-11-efp-lexis-config` (tip `2106d8fc1`, base `dev` @ b4e4ca5b2)
- **Reviewed:** 2026-08-31 · **Scope:** 5 commits, 9 files, +1037/-0
- **Verdict:** REQUEST CHANGES
  (Sound exploratory draft with an honest, well-scoped design note, but the new preset dir breaks an existing preset name (C1) and the documented laptop-flow discovery route silently fails (M1); both must be fixed before this is usable/mergeable.)

## 1. Summary

The branch adds a draft EFP/LEXIS submission path for JUPITER (JSC): a new TBG preset `etc/picongpu/efp-jupiter-jsc/` (profile + self-contained SLURM job-script template), docs (a new "Running on EFP" page, `profile.rst`/`tbg.rst` entries), a changelog entry, and 7 quick tests — with **zero runner changes**. The core mechanics verify well: the template renders through the real `tbg` (no unresolved `!var`, `bash -n` clean), the "simulated EFP execution context" (stub `srun`, dataset-shipped profile) reproduces the author's claims exactly in both the positive and negative cases, and the full PICMI → `write_input_file` → `tbg` → simulated-job E2E works when the preset is selected via `$XDG_CONFIG_HOME`. There is no lexis-cwl/Py4Lexis code or workflow definition in this branch (and none is pinned in the venv): "LEXIS" is reached purely through the EFP portal's job-script upload path, so there is no LEXIS-spec surface to validate here — the untested part is correctly and clearly fenced off in FINDINGS §7/§8. The two blocking problems: (1) the new directory name `efp-jupiter-jsc` makes the pre-existing short-form preset selection `preset="jupiter-jsc"` (and 8 other strings) ambiguous → hard `ValueError` regression; (2) the new doc tells users to put `picongpurc.toml` "next to the PICMI script", but the inherited CWD search only matches dotfiles, so that route silently produces a setup **without** the EFP preset (empty bare profile, no module stack on the compute node) and no local error. Minor: pre-commit is red at the branch tip (contradicting the "all hooks passed" claim) and two of the three touched RST pages have structural defects (contradicting the "RST parses" claim).

## 2. Findings

### 2.1 Critical

**C1** — **`etc/picongpu/efp-jupiter-jsc/` breaks selection of the pre-existing `jupiter-jsc` preset.**
- **`etc/picongpu/efp-jupiter-jsc/` (dir name) vs `lib/python/picongpu/_rc_params.py:167`** — The substring matcher in `_preset_path` filters with `f"{preset}/" in str(p)`. `"jupiter-jsc/"` is a substring of `"efp-jupiter-jsc/efp_picongpu.profile.example"`, so `RCParams(preset="jupiter-jsc")` now matches **two** presets and raises `ValueError`. On `dev` the same call resolves uniquely.
  - *Evidence:*
    ```
    $ python -c "from picongpu._rc_params import RCParams; RCParams(preset='jupiter-jsc')"
    ValueError: The given preset='jupiter-jsc' is ambiguous
      (candidates=['efp-jupiter-jsc/efp_picongpu.profile.example', 'jupiter-jsc/gh200_picongpu.profile.example'])
    ```
    Sweeping all plausible preset strings (dir names, file stems, prefixes) against the `dev` vs branch preset lists, **9 strings regress**, incl. `jupiter-jsc`, `jupiter`, `jup`, … (each: 1 candidate on dev → 2 on branch). The new test (`test_efp_preset_resolves_unambiguously`) only pins the fully-qualified form `jupiter-jsc/gh200_picongpu` — which is why the suite stayed green.
  - *Why it matters:* the directory-name form is a supported selection mechanism (see the `_preset_path` docstring example `preset = "bash"` and `RCParams.preset_dir`, which is how `generate()` copies the preset). Anyone with `preset = "jupiter-jsc"` in a `picongpurc.toml` or script gets a hard failure after this change — exactly the "behavior change for existing systems" the task's suggested approach rules out. Note the collision is **systematic**: any future `efp-<system>` preset mirroring an existing dir name (`efp-juwels-jsc`, `efp-lumi-eurohpc`, …) will break `<system>` the same way.
  - *Suggested fix:* anchor the directory match at `_rc_params.py:167`:
    ```python
    candidates = list(filter(lambda p: str(p).startswith(f"{preset}/"), get_available_presets())) or list(
        filter(lambda p: preset in str(p), get_available_presets())
    )
    ```
    (`startswith` keeps the documented `preset = "bash"` → `bash/…` behavior, since `bash-devServer-hzdr/…` does not start with `bash/`.) Add regression tests `RCParams(preset="jupiter-jsc")` and `RCParams(preset="jupiter")` asserting they still resolve to `jupiter-jsc`.
  - *Alternative:* rename the new preset dir to a name that does not contain any existing preset name as a substring (e.g. `efp-gh200-jsc`). This works for this one preset but defers the same bug to the next `efp-<system>` that mirrors an existing system — prefer the matcher fix.

### 2.2 Major

**M1** — **The documented "picongpurc.toml next to the PICMI script" discovery route silently fails; following the new doc literally yields a setup without the EFP preset.**
- **`docs/source/pypicongpu/running_on_efp.rst:77-78`** (with root cause in the inherited `lib/python/picongpu/_rc_params.py:638`) — The doc instructs: "Select the EFP preset in `picongpurc.toml` (**next to your PICMI script**, or in `$XDG_CONFIG_HOME/picongpu/picongpurc.toml`)". But `generate_default_rc_params()` finds CWD-relative files via `search_for_in_parents("[.]*picongpurc.toml", Path())`, and the glob `[.]*picongpurc.toml` matches only **dot-prefixed** names.
  - *Evidence:*
    ```
    $ python -c "from pathlib import Path; print(list(Path('.').glob('[.]*picongpurc.toml')))"   # cwd contains picongpurc.toml
    []
    ```
    E2E repro: running the PICMI script from a dir containing a plain `picongpurc.toml` (`preset="efp-jupiter-jsc"`) gives `rc_params.get("picongpurc_path") is None` → `write_input_file()` generates a setup whose `workflow/scripts/picongpu.profile` is the 10-line fallback (PATH export only — **no** module stack, no `TBG_SUBMIT`/`TBG_TPLFILE`, no `PIC_BACKEND`), and `preset_dir` is `""` (which silently copies *all* preset dirs). No error is raised. The job would then source a useless profile on the compute node and the staged binary would not find its runtime libraries.
    The `$XDG_CONFIG_HOME/picongpu/picongpurc.toml` route (second option in the same sentence) **does** work — I reproduced the full flow that way: bare profile renders with the complete EFP preset content, and the simulated job runs.
  - *Suggested fix:* (a) correct the doc: the reliable laptop route is `$XDG_CONFIG_HOME/picongpu/picongpurc.toml` (or `RCParams(preset=...)` / `RCParams(picongpurc_path=...)` in the script); state that a `picongpurc.toml` placed next to the script is **not** auto-discovered (only a dot-prefixed `.picongpurc.toml` is). (b) Re-run and re-word the FINDINGS §6.5/§6.6 E2E claim to name the route actually used — as written, "PICMI script + picongpurc.toml → setup contains the preset + … bare profile" is only reproducible via XDG/explicit path. (c) Optionally fix the inherited glob to also match `picongpurc.toml` (2-line change, benefits all presets) — if so, re-verify this E2E end-to-end through the fixed discovery.
  - *Alternative:* make `Simulation.write_input_file`/`Runner` discover `picongpurc.toml` relative to the calling script file instead of CWD — larger change, out of scope for this draft, but worth noting since CWD-based discovery is fragile for the "run the script from anywhere" promise.

### 2.3 Minor

**m1** — **`pre-commit run --all-files` is red at the branch tip; the "all hooks passed" claim is stale.**
- **`TASK-11-FINDINGS.md`** — the `require-ascii` hook (`.pre-commit-config.yaml:74`, excludes only rst/CHANGELOG/.zenodo.json/one .py file) fails on 35 non-ASCII lines in the findings doc (`→`, `—`, `↔`, `–`).
  - *Evidence:* full `pre-commit run --all-files` on a read-only archive of the tip: `Check file encoding ... Failed` (only failing hook); the same run on the previous commit `5f342a4a9` (before the findings doc was added in `2106d8fc1`) passes. So FINDINGS §6.7 "pre-commit run --all-files → all hooks passed" describes a pre-tip state.
  - *Suggested fix:* strip the non-ASCII characters from `TASK-11-FINDINGS.md` (or add `TASK-*.md` to the hook's `exclude` if task artifacts are meant to be exempt) and re-run at the tip.

**m2** — **`docs/source/pypicongpu/running_on_efp.rst:116-123` — RST "Unexpected indentation" (docutils ERROR/3).**
- Lines 116–123 ("This creates ``$SCRATCH/efp-run/…`` / Per-run overrides …") are indented 4 spaces while the enclosing list-item paragraph (lines 114–115) uses 3 spaces.
  - *Evidence:* docutils RST parse of the file: `L116 (ERROR/3) Unexpected indentation`. Sphinx will warn and the paragraph will be mis-rendered/split. This also falsifies the FINDINGS §6.8 claim that the RST of the new pages parses.
  - *Suggested fix:* re-indent lines 116–123 to 3 spaces (matching lines 114–115).

**m3** — **`docs/source/install/profile.rst:177-178` — section title underline too short.**
- The new sub-heading `Queue: booster (4 x Nvidia GH200 per node)` (42 chars) has a 38-char `^^^` underline.
  - *Evidence:* docutils parse: `L178 (WARNING/2) Title underline too short` — the heading is not parsed as a section.
  - *Suggested fix:* extend the underline to 42 chars (match the sibling "Queue: gpus (4 x Nvidia V100 GPUs)" section style).

### 2.4 Nits

**n1** — **`docs/source/pypicongpu/running_on_efp.rst:114`** — "(After sourcing the profile, `tbg -c etc/picongpu/N.cfg …` uses the preset defaults.)": sourcing the EFP profile *on the laptop* is not practical (it runs `jutil`/`module load`, which don't exist there). The explicit `-t` form given in the same step already works without sourcing; either drop the parenthetical or say the alternative is `export TBG_TPLFILE=…` for convenience.

**n2** — **`docs/source/pypicongpu/running_on_efp.rst` (Configurability section)** — the page never states that `picongpu_run()` (the CWL workflow) is *not* the EFP submission path. With the EFP preset, `run_submit_system` defaults to the profile's `TBG_SUBMIT=sbatch` (`runner.py:141-145` → `run.cwl` submit step), so running the CWL flow from a laptop fails at `sbatch`. One sentence ("the CWL runner is for local/SLURM execution; for EFP, upload the rendered script + `input/` via the portal") would prevent confusion.

## 3. Requirement traceability

| # | Requirement (from task file) | Status | Where / note |
|---|---|---|---|
| 1 | Configurable target system: preset per system `efp-<system>`, selectable via `picongpurc.toml` and/or `RCParams`/`TBGFlags` | **partial** | Works via `RCParams(preset=…)`, `TBGFlags`, and XDG `picongpurc.toml` (verified E2E); the documented "next to the script" toml route silently fails (M1); new preset regresses existing `jupiter-jsc` selection (C1) |
| 2 | Per-run overrides (queue/account/walltime) via `overwrite_vars` without new machinery | **met** | `tbg -o "TBG_queue=debug TBG_wallTime=01:00:00"` verified in render; CWL `o=[…]` rejection is pre-existing (FYI, author-noted) |
| 3 | (a) Self-contained job script in target batch dialect, uploadable as-is | **met (draft)** | Renders via real `tbg`; simulated EFP-context run passes (pos+neg); "prints job id to stdout" is not done in-script — arguably covered by the EFP portal's job logs; platform pass-through of `#SBATCH` still unverified (§8.3, correctly flagged) |
| 4 | (b) Container path with trade-offs | **met (documented)** | FINDINGS §2(b) + EFP page: fallback, recipe sketch, not built — explicitly out of scope for the draft |
| 5 | (c) Py4Lexis path with trade-offs | **met (documented)** | FINDINGS §2(c): not implemented; sound compatibility argument (rendered script + `input/` are exactly Py4Lexis's inputs) |
| 6 | (d) Decide + document how the CWL runner drives the path | **partial** | Decision documented (no runner changes; CWL flow left for local use) but the doc doesn't warn that `picongpu_run()` is not the EFP path (n2) |
| 7 | Staging compatibility documented + template-supported | **met (draft)** | §4/§7 of FINDINGS + EFP page map `input/` ↔ `./input`, `simOutput` ↔ output dataset; template pins cwd via `TBG_dstPath="$(pwd)"` and sources the dataset profile; portal semantics pending (§8) |
| 8 | Docs: EFP page + `profile.rst` + `tbg.rst` note | **partial** | All three added; RST defects m2/m3; discovery instruction wrong (M1) |
| 9 | Verification: local-first + one EFP smoke run when access available | **partial** | Local loop is thorough and mostly reproducible (see §4); smoke run honestly deferred with concrete plan + success criteria (FINDINGS §7) and correct open questions (§8) |
| 10 | Changelog entry | **met** | 0.9.0 entry, style consistent with 0.8.0 |

## 4. Claim verification (author artifact)

| Claim (from TASK-11-FINDINGS.md) | Re-verified? | Result / delta |
|---|---|---|
| Test gate: 181 passed (baseline 174 + 7 new), 2 xfailed, 1 xpassed | yes | **Matches**: `181 passed, 2 xfailed, 1 xpassed` re-run in the task venv |
| "tbg render works" (valid job script, no unresolved vars, `bash -n` OK) | yes | **Verified** with the real `bin/tbg`: no unresolved `!var`, `bash -n` clean, SLURM lines correct |
| "Simulated EFP execution context" (profile sourced from dataset, `simOutput/` + `output` symlink, `picongpu` launched with full params; missing `input/` → clear error, exit 1) | yes | **Verified** — both minimal render and full E2E (real generated `-d 1 1 1 -g 32 32 32 -s 4 --periodic 0 0 1 …` params). Note: this is a local **shell** simulation (stub `srun`/`jutil`/`module`), not a lexis/tbg mock — there is no lexis or py4lexis package in the venv and no LEXIS workflow file in the diff; the claim is honestly scoped as such in §6/§7/§8 |
| Per-run overrides via `tbg -o` | yes | **Verified** (`--partition=debug`, `--time=01:00:00` in rendered script) |
| CWL compatibility: `submit.sh` sed rewrites `TBG_dstPath=` / `--chdir=` correctly with the new template | yes | **Verified**: `TBG_dstPath="$(pwd)"` → `TBG_dstPath=<workdir>`; no `--chdir` line (only a comment mentions it) → second sed is a no-op |
| Full laptop flow E2E: "PICMI script + `picongpurc.toml` (`preset = "efp-jupiter-jsc"`) → setup contains the preset + rendered `N.cfg` + bare profile; simulated run launches with real params" | **partially** | Reproducible **only** via `$XDG_CONFIG_HOME/picongpurc.toml`; via the doc's primary "next to the script" route the preset is not discovered and the bare profile is the empty fallback (M1) |
| "Preset selection: … and `picongpurc.toml`-based selection all resolve" (§6.6) | **partially** | True for XDG/explicit `picongpurc_path`; not for the CWD/next-to-script route (M1). Also, the short forms `jupiter-jsc`/`jupiter` of the *pre-existing* preset no longer resolve (C1) — the "unambiguous" test only pins the fully-qualified form |
| "pre-commit run --all-files → all hooks passed" (§6.7) | **no** | Red at tip: `require-ascii` fails on `TASK-11-FINDINGS.md` (35 non-ASCII lines); passes at the previous commit (m1) |
| "RST of the new/changed pages parses (docutils check)" (§6.8) | **no** | `running_on_efp.rst:116` ERROR (unexpected indentation, m2); `profile.rst:178` WARNING (underline too short, m3); `tbg.rst`/`index.rst` clean |
| "Profile rendering requires `author`/`email`/`pic_libs` as with all presets" (§6.6) | yes | `required_information == [author, email, pic_src_path, pic_libs]`; `pic_src_path` has a built-in default, consistent with other presets |
| Docs build not run end-to-end (Doxygen/breathe unavailable) | n/a | Acknowledged limitation; full Sphinx build not reproducible in this container |

## 5. Design discussion

**Chosen mechanism (job script, zero runner changes) is the right one for this codebase.** The repo's submission machinery (TBG `.tpl`/`.cfg`, `etc/picongpu/<system>` presets, `RCParams`/`TBGFlags` plumbing) is exactly the carrier the task file anticipated, and the draft exploits it without touching `runner.py` or the CWL templates. The trade-off comparison (a) job script / (b) container / (c) Py4Lexis / (d) runner integration is honest: each path's real costs (arch-specific pre-built binary + multi-GB SIFs + GPU pass-through; new dependency + credentials + evolving API) are stated, a primary path is recommended, and the fallback is kept compatible. The "configurable target system" promise is a genuine mechanism, not a veneer: no JUPITER-specific code, the preset dir drives `TBG_SUBMIT`/`TBG_TPLFILE`/profile, and per-run overrides work through the existing `-o`/`overwrite_vars` machinery — but see C1: the *naming convention* `efp-<system>` collides systematically with the substring preset matcher whenever `<system>` mirrors an existing dir name (it would again for `efp-juwels-jsc`, `efp-lumi-eurohpc`, …). A maintainer should weigh the matcher fix (root cause, ~2 lines + regression test) against renaming; the latter only delays the next collision.

**Where the draft is weakest:** the user-facing flow. The task's core promise is "picongpurc.toml + PICMI script on the laptop → running the script handles the rest". The mechanism exists and works (XDG route verified end-to-end), but the *primary documented* discovery route is silently broken (M1) — and the failure mode (empty bare profile → job dies on the cluster, not on the laptop) is the worst kind for a first-time EFP user. Second, the doc doesn't demarcate the CWL/`picongpu_run()` flow from the portal-upload flow (n2). Third, the verification story is honest but the two "green" claims that are checkable locally (pre-commit, RST) don't hold at the tip — for an exploratory draft, the local loop is supposed to be the trust anchor.

**What deserves trust:** the EFP-platform unknowns (execution-context cwd, `./input` staging, `#SBATCH` pass-through, account/QoS, dataset limits) are explicitly fenced as pending in §7/§8 with concrete smoke-run steps and success criteria, and none of the local claims lean on them. The simulated run verifies exactly what it claims — the rendered script's behavior under the *assumed* execution context — and no more. The JSC dialect choice (SLURM `sbatch`, as in the existing `juwels-jsc`/`jupiter-jsc` templates) is correct for JUPITER; no lexis-cwl surface exists to get wrong.

**Alternative designs worth noting** (not required for this draft): (1) a `submit_system="efp"` value in `TBGFlags` with a new CWL step that shells out to Py4Lexis once the API is pinned — the artifact set (rendered script + `input/`) is already its input, so this slots in cleanly later; (2) fixing `search_for_in_parents` to match both `picongpurc.toml` and `.picongpurc.toml`, which would make the documented next-to-script route actually work for all presets; (3) anchoring `_preset_path` directory matching (C1 fix) so the `efp-<system>` convention is safe by construction.

## 6. Prioritized next steps

1. **Fix C1**: anchor the `_preset_path` directory match (`str(p).startswith(f"{preset}/")`) and add regression tests for `RCParams(preset="jupiter-jsc")` and `RCParams(preset="jupiter")`; confirm `pytest quick/` stays 181+green.
2. **Fix M1**: correct `running_on_efp.rst` to document the working discovery route(s) (XDG / explicit `RCParams`), re-run the laptop E2E through the *documented* route, and re-word FINDINGS §6.5/§6.6 to name the route used. (Optionally also fix the inherited dotfile-only glob and re-verify.)
3. **Fix the RST defects** (m2: re-indent `running_on_efp.rst:116-123`; m3: lengthen the `profile.rst:178` underline) and re-run the docutils check on all touched pages.
4. **Make pre-commit green at the tip** (m1): strip non-ASCII from `TASK-11-FINDINGS.md` (or exclude `TASK-*.md` in the hook) and re-run `pre-commit run --all-files`.
5. **Doc clarifications**: n1 (drop/clarify the "after sourcing the profile" parenthetical) and n2 (state that `picongpu_run()`/CWL is not the EFP submission path; `run_submit_system` will be `sbatch`).
6. Proceed to the §7 EFP smoke run once EFP access is available; §8's open questions (target systems/dialects, JSC project/budget + QoS, execution-context cwd, dataset limits) are the right checklist for what that run must confirm.

## FYI (inherited from base, not scored here)

- `lib/python/picongpu/_rc_params.py:638` — `search_for_in_parents("[.]*picongpurc.toml", Path())` matches only dot-prefixed files, so a plain `picongpurc.toml` next to the script is never auto-discovered (root cause of M1's doc mismatch).
- `etc/picongpu/jupiter-jsc/gh200_picongpu.profile.example:124` — `getDevice()` uses `--mem=$((117760 * numGPUs))` (undefined var → 0); the new EFP profile fixes this for its copy (`$numDevices`), but the original preset still carries the bug.
- `docs/source/usage/tbg.rst:87,96` — the `include` of `../install/profiles/taurus-tud/Slurm_Tutorial.rst` and `summit-ornl/LSF_Tutorial.rst` reference files that do not exist (docs build warnings); pre-existing on `dev`.
- `lib/python/picongpu/templates/workflow/steps/run.cwl` `overwrite_vars: string?` vs `TBGFlags.overwrite_vars: list[str]` (`runner.py:151-155`) — `picongpu_run(o=[…])` is rejected by cwltool; pre-existing, correctly noted by the author in FINDINGS §3.
- `#SBATCH --mincpus=!TBG_mpiTasksPerNode` in the JSC-family templates (incl. the new one, copied verbatim) — not a standard `sbatch` option as far as the review could tell; unverified, pre-existing.
