# Review - Task 12: general, portable installation of compiled build dependencies

- **Branch:** `task-12-deps-autoinstall` (tip `07ced64b1`, base `dev` @ `b4e4ca5b2`)
- **Reviewed:** 2026-08-31 · **Scope:** 4 commits, 13 files, +2053/-401
- **Verdict:** REQUEST CHANGES
  (the feasibility report is solid and its claims survived re-verification, and the default workflow output is byte-identical - but the draft installer's *primary* full-stack path is broken in two ways (C1, C2), the per-cluster "drop-in replacement" claim does not hold (M1, M2), and two cache-integrity gaps (M3, M4) contradict the documented semantics.)

## 1. Summary

The branch generalises the three per-cluster `dependencies_autoinstall.sh` scripts into a parameterised, toolchain-keyed, cache-backed installer (`etc/picongpu/dependencies/picongpu-deps.sh` + 832-line lib), adds thin per-cluster wrappers, an opt-in `[dependencies]` table in `picongpurc.toml` wired into the generated build/prepare/submit scripts, a DRAFT (unwired) CWL step, docs, and a 321-line findings report. The report is the strongest part: I re-verified the subset-build timings (175 s cold / 0.17 s warm), the "CMake finds all dependencies" claim (re-ran the author's scratch project against the author's prefix), the conda-forge availability table (7/8 present, PNGwriter 404), and the "no default behaviour change" claim (full generated-workflow diff vs `dev`: zero differences; test gate 187 passed vs 174 baseline). The draft implementation, however, has two critical bugs on the full-stack path - a missing `deps_install_c-blosc2` function that aborts every default run after Boost (C1), and a Boost build whose failures are swallowed and stamped as success (C2) - plus a set of major robustness and claim-accuracy problems: the three "fixed" profile drift bugs are still in the profiles (M1), managed-mode installs are silently invisible whenever any profile `*_ROOT` is set (M2), interrupted downloads poison the source cache (M3), and version overrides are ignored by the git source cache (M4). For an exploratory draft, the report and the managed-mode subset flow are genuinely usable; the "replaces the per-cluster scripts" deliverable is not yet usable as-is.

Most important issues:
1. **C1** - `deps_provider_source` looks up `deps_install_$key`; for key `c-blosc2` the function is named `deps_install_c_blosc2`, so every default (no `DEPS_ONLY`) run - i.e. all three cluster wrappers and the default runner-enabled path - aborts at the 2nd of 8 dependencies after building Boost.
2. **C2** - `deps_install_boost` runs bootstrap/b2 in a subshell without any rc check and then stamps unconditionally: a failed Boost build is reported as success and the empty target is cached as "installed" (verified: stamp on a directory containing nothing but the stamp).
3. **M1/M2** - the claimed profile-drift fixes were never made (profiles are not in the diff), and in every real cluster profile (which exports 5-7 of the 8 `*_ROOT` vars) at least one dependency falls into managed mode whose environment file is never generated - FFTW3 is silently lost on rosi/delta, and perlmutter's ADIOS2/openPMD are silently rebuilt against a source-built HDF5 that is never on the runtime `LD_LIBRARY_PATH`.

## 2. Findings

### 2.1 Critical

**C1 - full-stack run aborts at `c-blosc2`: function-name/key mismatch.**
- **`etc/picongpu/dependencies/picongpu-deps-lib.sh:734`** - `local fn="deps_install_$key"` with `key=c-blosc2` yields `deps_install_c-blosc2`; the actual function is `deps_install_c_blosc2` (line 420). A command name with a dash can never match the function, so `"$fn"` -> "command not found" (rc 127) -> provider loop aborts: libpng, pngwriter, hdf5, adios2, openpmd, fftw3 are never attempted.
  - *Evidence:* ran `deps_provider_source` with a warm fake cache and the lib sourced (as the real script does): boost built for 77 s (real download + build, proving the rest of the path works), then `picongpu-deps-lib.sh: line 735: deps_install_c-blosc2: command not found` -> `WARNING: c-blosc2: build failed; aborting remaining dependencies`, `provider_source rc=1`. The author's own subset test used `DEPS_ONLY=fftw3,libpng,pngwriter,hdf5,openpmd` - c-blosc2 was never exercised, which is how this shipped.
  - *Impact:* the default invocation (`bash picongpu-deps.sh` - what all three cluster wrappers and the default `[dependencies].enabled = true` runner path do) is broken on every machine, cluster or laptop. The "replace the 3 duplicated scripts" deliverable does not work as-is.
  - *Suggested fix:* map key->function explicitly, e.g.
    ```bash
    declare -A DEPS_FN=([boost]=deps_install_boost [c-blosc2]=deps_install_c_blosc2 ...)
    local fn="${DEPS_FN[$key]}"
    ```
    and add a quick test that runs `deps_provider_source` over **all** keys with stubbed install functions (or at least asserts `type "deps_install_$(tr '-' '_' <<<"$key")" >/dev/null` for every key) - the 13 new tests never call the provider loop with the full key set.

**C2 - failed Boost build is stamped as installed (silent cache poisoning).**
- **`etc/picongpu/dependencies/picongpu-deps-lib.sh:407-418`** - the build runs in a subshell `( cd "$src"; ./bootstrap.sh ...; ./b2 ...; ./b2 install )` whose exit status is discarded (it is not the last command and is not wrapped in `deps_build`/`|| return 1`); `deps_stamp` and `deps_record "$key" 0 ...` then execute unconditionally.
  - *Evidence:* seeded the source cache with a boost tarball whose `bootstrap.sh` exits 1 and called `deps_install_boost` exactly as the provider loop does (conditional context, so `set -e` is suspended): output `bootstrap: simulated failure` -> `deps_install_boost returned SUCCESS`; the target directory contains **only** `.picongpu-deps.stamp`; summary records `boost|0|0`. A subsequent run hits the guard's "matching stamp -> cache hit, skipping" branch (lib:286-291), so the broken state is permanent until `DEPS_FORCE=1`.
  - *Impact:* violates the documented failure semantics (FINDINGS §6: "a failed build leaves no stamp and the script exits non-zero") and the idempotency contract. On a real cluster, a transient Boost failure (b2 OOM, disk full) would produce an empty `BOOST_ROOT` declared installed; `find_package(Boost 1.74 REQUIRED CONFIG)` then fails later in `pic-build` in a confusing way, and re-running the installer "fixes" nothing.
  - *Suggested fix:* route Boost through `deps_build` like the other seven deps (it also gains the missing build log and `DEPS_QUIET` handling), e.g.
    ```bash
    deps_build "$key" bash -c "cd '$src' && ./bootstrap.sh --with-libraries='$DEPS_BOOST_LIBRARIES' --prefix='$target' CC='$DEPS_CC' CXX='$DEPS_CXX' && ./b2 cxxflags=-std=$DEPS_CXXSTD -j '$DEPS_JOBS' && ./b2 install" || return 1
    ```
    (or rc-check the subshell: `local rc=0; ( ... ) || rc=$?; [ $rc -eq 0 ] || return 1`).

### 2.2 Major

**M1 - the "3 fixed profile drift bugs" were not fixed; the wrappers inherit the broken values.**
- **`etc/picongpu/rosi-hzdr/gpu-v100_picongpu.profile.example:53`** still `HDF5_VERSION=2.0.0 #1.14.6`; **`etc/picongpu/delta-ncsa/gpuA100x4_picongpu.profile.example:60`** the same; **`:95`** still `export FFTW_ROOT=$DELTA_LIB/FFTW/FFTW_VERSION` (missing `$`). The diff touches no profile file.
  - *Evidence:* `git diff dev...task-12-deps-autoinstall --stat` lists 13 files, none under `*profile*`; grep of the branch profiles shows all three drifts intact (rosi HDF5:53, delta HDF5:60, delta FFTW_ROOT:95).
  - *Consequences:* (a) `deps_resolve_version(hdf5)` falls back to the profile var -> `deps_fetch_git ... hdf5_2.0.0` -> tag does not exist -> clone fails -> the whole run aborts (old scripts aborted the same way via `wget` 404, so this is parity-of-broken, but FINDINGS §7.2 lists the fix as "done as a follow-up" - it is not done, and §1.2's drift list presents it as the *motivation* for the shared script); (b) delta's `FFTW_VERSION` typo means `FFTW3_ROOT` is never set (see M2) -> FFTW3 built into managed mode and never exposed - the old script's equally-broken `FFTW_ROOT` at least pointed CMake/CPATH/LD_LIBRARY_PATH at the literal directory it installed into, so the new flow is a *regression*, not parity.
  - *Suggested fix:* fix the profiles in this branch (one line each: `HDF5_VERSION=1.14.6`, `export FFTW_ROOT=$DELTA_LIB/FFTW/$FFTW_VERSION`) or, if deliberately deferred, rewrite FINDINGS §7.2 to say so, and have the wrappers pin the sane values (`export DEPS_HDF5_VERSION=${DEPS_HDF5_VERSION:-1.14.6}`) so a drifted profile cannot break the run. Also decide `FFTW_ROOT` vs `FFTW3_ROOT` (CMake honours `FFTW3_ROOT`, `include/picongpu/CMakeLists.txt:45`) and migrate the profiles.

**M2 - managed-mode installs are invisible whenever any `*_ROOT` is set; perlmutter's HDF5 provenance changes silently.**
- **`etc/picongpu/dependencies/picongpu-deps-lib.sh:753`** - `deps_write_env_file` is only called when *all eight* `*_ROOT` vars are empty. Any mixed cluster profile (all three are mixed) gets no env file, so every dependency that fell into managed mode is built and then consumed by nothing.
  - *Evidence (reproduced):* with `OPENPMD_ROOT` set (simulating rosi/delta's profiles, which export 7 of the 8 roots) and `DEPS_ONLY=libpng`, `deps_provider_source` returns 0, installs libpng under the managed root, and `current.env` does not exist. Mapped against the actual profiles: rosi/delta export `ADIOS2_ROOT BLOSC_ROOT BOOST_ROOT FFTW_ROOT HDF5_ROOT LIBPNG_ROOT OPENPMD_ROOT PNGwriter_ROOT` but **not** `FFTW3_ROOT` -> fftw3 -> managed -> never exposed (FFTW3/Shadowgraphy silently absent); perlmutter exports only 5 roots -> **libpng, hdf5, fftw3** -> managed -> never exposed.
  - *Worse for perlmutter:* the old script *skipped* libpng/HDF5/FFTW (site modules provide HDF5) and built ADIOS2/openPMD against the module's HDF5. The new wrapper (no `DEPS_ONLY` restriction) now builds a source HDF5 in managed mode, and `deps_install_adios2` (lib:561-577) hints ADIOS2 at that managed prefix - so ADIOS2/openPMD end up linked against `~.../picongpu-deps/<key>/hdf5-1.14.6/lib` which is on **no** `LD_LIBRARY_PATH` at runtime (profile unchanged, no env file). A previously working cluster flow becomes a runtime library-load failure, silently.
  - *Impact:* contradicts the wrapper docstrings/README ("This reproduces the old per-cluster behaviour") and the task verification criterion "reproduces today's rosi/delta/perlmutter installs ... (or documented deviation)" - these are deviations, and they are undocumented.
  - *Suggested fix:* track whether *any* dependency was installed in managed mode and write the env file whenever that happens (merge managed hints with the cluster `*_ROOT` hints); or fail fast in mixed mode ("profile sets HDF5_ROOT but not FFTW3_ROOT: set DEPS_ONLY or fix the profile"). For perlmutter specifically, the wrapper should restore the old scope: `export DEPS_ONLY=${DEPS_ONLY:-boost,c-blosc2,pngwriter,adios2,openpmd}` (modules provide libpng/HDF5/FFTW) - and should default `DEPS_CMAKE_EXTRA_ADIOS2`/`DEPS_CMAKE_EXTRA_OPENPMD` to the `-DMPI_mpi_gnu_123_LIBRARY=${MPICH_DIR}/lib/libmpi_gnu_123.so` flag the old script passed (currently only a commented-out example in all three wrappers).

**M3 - interrupted download permanently poisons the source cache (no rc check, no checksums).**
- **`etc/picongpu/dependencies/picongpu-deps-lib.sh:222-238`** - `deps_fetch_tarball` runs `curl -fL ... -o "$dest.part"` (or `wget`) **without checking the exit status**, then unconditionally `mv "$dest.part" "$dest"`. The function even returns 0 afterwards. On a network interruption (curl exit 18/56 - routine on cluster login nodes), the partial file is moved to the final name and every later run reports "source cache hit" for a corrupt tarball; there is no checksum, size, or `tar -t` validation anywhere.
  - *Evidence:* stubbed `curl` writing 15 bytes and exiting 18 (mid-transfer); result: `deps_fetch_tarball` rc=0, `libpng-1.6.34.tar.gz` cached as `partial garbage`, reported CORRUPT by `tar -tzf`.
  - *Impact:* for a "portable for all clusters" installer whose whole selling point is fetch-once-on-login + `--offline` compute, one flaky transfer makes the shared cluster cache unusable for everyone who shares `DEPS_SOURCE_CACHE`, with no diagnostic.
  - *Suggested fix:* `curl ... || { rm -f "$dest.part"; deps_die "..."; }` (never `mv` on failure), download to a temp name, verify (`sha256sum -c` against a pinned hash per dependency - the dependency table is static, so pinning hashes is cheap and also defends against MITM on restricted clusters), then `mv` into place.

**M4 - git source cache ignores the requested tag; version overrides silently build the wrong version.**
- **`etc/picongpu/dependencies/picongpu-deps-lib.sh:240-252`** - cache-hit test is `if [ -d "$dir/.git" ]` (name only). If the clone for `v2.22.0` already exists, a later run with `DEPS_C_BLOSC2_VERSION=2.23.0` (a headline feature - `DEPS_<NAME>_VERSION` / `[dependencies].versions`) reports "source cache hit", copies the **v2.22.0** tree, builds it, and stamps `version=2.23.0`.
  - *Evidence:* seeded a bare git cache cloned at tag `v2.22.0`; second call requesting `v2.23.0` -> `source cache hit: git:c-blosc2`; `git describe` in the cached checkout: `v2.22.0`.
  - *Impact:* fingerprint/key include the *requested* version, so the key changes too, but the built artifact is the old version; the stamp lies. Anyone pinning a version bump (exactly the use case the config surface advertises) gets silently stale binaries.
  - *Suggested fix:* key the cache dir by tag (`git/$name-$tag`) or, on hit, verify `git -C "$dir" describe --tags` equals the requested tag and `git checkout`/`fetch` otherwise.

### 2.3 Minor

**m1 - `set -eu -o pipefail` (no `-u`).** `picongpu-deps.sh:36`; the old per-cluster scripts used `set -euf -o pipefail`. For a script that dereferences many `DEPS_*` variables, `-u` catches typos at the point of use (several of the bugs found here would have been louder). Add `-u` and audit the handful of unguarded expansions.

**m2 - compiler default ignores `$CC`/`$CXX` and looks up a literal binary named `CC`.** `picongpu-deps.sh:185` `DEPS_CXX=${DEPS_CXX:-$(command -v CC || command -v c++ || ...)}` - `command -v CC` searches PATH for an executable *named* "CC" (never present); it inherited the old scripts' `$(which CC)` defect. On sites where the loaded toolchain exports `CC`/`CXX`, dependencies are built with bare `cc`/`c++` while PIConGPU may be built with the module compiler -> potential libstdc++/ABI mismatch, and the toolchain key (which hashes `DEPS_CC/DEPS_CXX --version`) does not reflect PIConGPU's actual frontend, so the "key prevents mixing" guarantee (FINDINGS §2.1.6) has a hole. Default to `${CC:-cc}` / `${CXX:-c++}`.

**m3 - the summary's "FAILED after Xs" branch is unreachable.** `picongpu-deps-lib.sh:816-831` vs `:735-742` - `deps_record` is only ever called with rc 0 on the success path; a failed dependency is warned about and then omitted from the summary entirely (confirmed in the C1 repro: summary listed `boost` only, no c-blosc2 entry). Record the failure (`deps_record "$key" 1 $((SECONDS - t0))` before breaking) so the summary tells the truth.

**m4 - dead code / under-used escape hatches.** `picongpu-deps-lib.sh:522-524` (`mpi_flags` local populated, never used); `DEPS_CMAKE_PREFIX_HINT` is documented as a general knob (README:101, `--help`) but only `deps_install_c_blosc2` (lib:439) consumes it - pngwriter/hdf5/adios2/openpmd use their own local hint logic. Either wire it through or narrow the docs.

**m5 - non-`source` providers are silent no-ops in the runner.** `lib/python/picongpu/dependencies.py:103-105` - `active = enabled and provider == "source"`, so `[dependencies] enabled=true, provider="conda"|"modules"|"container"` generates nothing, with no warning, even though the toml schema comment (dependencies.py:19) advertises all four. Either emit a log line in the generated build script ("provider 'conda' is not wired yet; doing nothing") or reject the combination in `from_rc_params`.

**m6 - `current.env` is a last-writer-wins global; cross-toolchain runs flip it; the "different key -> skip" guard is unreachable in managed mode.** A run under a *new* toolchain (e.g. different MPI loaded) computes a new key, **rebuilds everything** into a fresh `<key>/` tree (verified: under a no-MPI toolchain the run rebuilt libpng+pngwriter before failing on hdf5), and on success `cp`'s its env over `DEPS_INSTALL_ROOT/current.env` - silently re-pointing every consumer (generated build/prepare/submit scripts source `current.env`) at the other toolchain's binaries. The guard branch "exists but was built for a different toolchain -> skip" (lib:289-294) can only trigger in cluster mode, because managed targets are per-key (`$DEPS_INSTALL_ROOT/$DEPS_KEY/...`); README:73-76 nonetheless states the skip behaviour generally. Consider pinning the key in the generated scripts (recompute the key inside build.sh after toolchain load and source `<key>/picongpu-deps.env`), or at minimum warn when overwriting `current.env` with a key different from the one it currently holds.

**m7 - wrappers evaluate `$ROSI_LIB`/`$DELTA_LIB` before the profile is sourced.** e.g. `etc/picongpu/rosi-hzdr/dependencies_autoinstall.sh:37` sets `DEPS_SOURCE_CACHE=${DEPS_SOURCE_CACHE:-"$ROSI_LIB/deps-sources"}` while only checking that `$PIC_PROFILE` *is a file*; the shared script sources the profile later. If the user set `PIC_PROFILE` without sourcing the profile (a flow the shared script explicitly supports, `picongpu-deps.sh:170-176`), `$ROSI_LIB` is empty in the wrapper -> cache defaults to `/deps-sources` (filesystem root). Default the cache after sourcing the profile, or require the lib var to be non-empty.

**m8 - no-MPI case: warns, then fails late.** `picongpu-deps.sh:220-222` warns "parallel HDF5/ADIOS2/openPMD cannot be built - fine for a minimal subset" but still proceeds; with `DEPS_ONLY=hdf5,openpmd` the run builds the cheap deps first and dies at HDF5's CMake configure (`Could NOT find MPI`, reproduced). Abort early (or auto-restrict `DEPS_ONLY`) when MPI is absent and a parallel-stack dep is requested.

**m9 - docs section landed in the legacy root `INSTALL.rst`, not the live install page.** The new "Automatic Installation of Dependencies" section was appended to the repo-root `INSTALL.rst` (last touched by an old commit `ab686b5b3`, not referenced by any docs toctree since the docs restructure `ccb2df042` moved install docs to `docs/source/install/`), and its `literalinclude:: profiles/dependencies/...` paths do not resolve from that location (no `profiles/` at repo root; `docs/source/install/profiles/` has no `dependencies/` subdir). The actual dependency-install page, `docs/source/install/dependencies.rst`, is untouched. Move the section there with resolvable include paths (the task explicitly asks for a "dependency installation" section on the install page).

### 2.4 Nits

**n1 - `bash -c "cd '$src' && ..."` string interpolation** (`picongpu-deps-lib.sh:463`, `:659`) breaks on any single quote in `DEPS_INSTALL_ROOT`; pass the path via an env var or use a subshell like the (to-be-fixed) boost path.

**n2 - `install_dependencies.cwl`:** `baseCommand: ./install.sh` requires the input `File` to carry the executable bit (InitialWorkDir does not chmod it); and `outputs.deps_directory` globs `"deps"` in the workdir, which matches almost no real configuration (the doc admits this). Both are fine for a DRAFT stub, but the stub will mislead its first user.

**n3 - FINDINGS §4 inaccuracies:** lists `docs/source/install/dependencies.rst` as part of this branch's structure (it predates the branch, commit `ccb2df042`) and says the test file has "11 tests" (it has 13; 174 + 13 = 187 ok).

**n4 - `deps_list`'s "source" column is a placeholder** ("see README.md") - either drop the column or fill it (tarball URL / git ref) while the table is being maintained anyway.

## 3. Requirement traceability

| # | Requirement (from task file) | Status | Where / note |
|---|---|---|---|
| 1 | Feasibility analysis with evidence | met | FINDINGS §1-2; conda-forge table re-verified from the author's API-check JSONs (7 present, `pngwriter` -> `"could not be found"`); subset timings backed by author logs and re-run |
| 2 | Compare (a)-(d) with trade-offs + recommendation | met | FINDINGS §3; recommendation (d) with (a)+(b) implemented, (c) documented - matches the task's suggested shape |
| 3 | Effort estimate | partial | build-time extrapolation only (FINDINGS §5: +Boost/ADIOS2 approx. 10-30 min); no human effort estimate for cluster validation/iteration |
| 4 | Answer "is this undoable, and where" (per cluster) | met | FINDINGS §2.1.6: PNGwriter conda gap, no-compiler sites, binary-incompatibility trap; honest |
| 5 | Generalised parameterised script (option a) | partial | mechanism works for the managed-mode subset (verified end-to-end), but the default full path is broken (C1, C2) and cache integrity is weak (M3, M4) |
| 6 | Provider configuration in `picongpurc.toml` (option d) + CWL step wiring (option b) | met (opt-in, draft) | `dependencies.py` + `runner.py` hook, validated, default-off; CWL step deliberately standalone/DRAFT with the trade-off documented (FINDINGS §4, §7.4) - acceptable given the coordinator's note |
| 7 | Replace the duplicated per-cluster scripts (per-cluster overrides possible) | partial | thin wrappers exist and `DEPS_*` overrides are possible, but the default wrapper path aborts (C1) and behaviour deviates from the old scripts without documentation (M1, M2) - verification criterion "reproduces today's rosi/delta/perlmutter installs (or documented deviation)" not met |
| 8 | Local subset test loop + `CMAKE_PREFIX_PATH` wiring proven | met | re-verified: 175 s cold (author log `deps-final-cold.log` summary 10+4+65+64+32), 0.17 s warm (my re-run, all "cache hit, skipping"), scratch CMake project finds PNGwriter/openPMD(HDF5=TRUE)/FFTW3 3.3.10/MPI with only `current.env` sourced |
| 9 | Docs (install/profile page section) + changelog | partial | CHANGELOG ok; docs section added to legacy root `INSTALL.rst` with non-resolving `literalinclude` paths; live page `docs/source/install/dependencies.rst` untouched (m9) |
| 10 | Opt-in: default behaviour unchanged for existing workflows | met | full generated-workflow tree diff vs `dev` for a plain config: zero differences; test gate 187 passed |
| 11 | Verification: pytest quick green; pre-commit green | met / partial | 187 passed, 2 xfailed, 1 xpassed (re-run); pre-commit default-stage hooks checked manually (trailing ws / EOF / ASCII clean, shebangs executable); ruff/gersemi hooks are `stages: [manual, pre-push]` and ruff is not installed in this container, so not directly re-run |

## 4. Claim verification (author artifact)

| Claim (from TASK-12-FINDINGS.md / author report) | Re-verified? | Result / delta |
|---|---|---|
| quick suite 187 passed (baseline 174) | yes | `pytest quick/` -> `187 passed, 2 xfailed, 1 xpassed, 3499 subtests` - exact match; +13 = the new test file |
| subset build ~175 s cold on 16 cores | yes (from artifacts) | author's `deps-final-cold.log` summary: 10+4+65+64+32 s; install tree + stamps present in `/tmp/opencode/deps-prefix` |
| warm run 0.2 s (cache hit) | yes (re-run) | my re-run on a copy of the author's prefix with the same toolchain key: **0.170 s**, 5× "already installed ... (cache hit, skipping)". Caveat: no "cache hit" line appears in any log the author left - the warm run itself was not logged |
| CMake finds all dependencies via the generated env | yes | re-ran the author's scratch project (`/tmp/opencode/scratch-cmake`) with `current.env` + `module load mpi/openmpi-x86_64`: `Found PNGwriter .../pngwriter-0.7.0`, `Found openPMD ...(HDF5=TRUE, ADIOS2=FALSE)`, `Found FFTW3: 3.3.10`, `Found MPI: TRUE` |
| PNGwriter not on conda-forge (404); other 7 available | yes | author's API-check JSONs: 7 packages resolve, `pngwriter` -> `{"error":"\"pngwriter\" could not be found"}` |
| "fixed 3 profile drift bugs (rosi HDF5_VERSION, OPENPMD_ROOT guard, delta FFTW_VERSION)" (coordinator's framing of the author's claim) | **no** | profiles are not in the diff; rosi `HDF5_VERSION=2.0.0` (line 53) and delta `FFTW_ROOT=.../FFTW_VERSION` (line 95) - and delta `HDF5_VERSION=2.0.0` (line 60, not even in FINDINGS §1.2) - all intact. Only the old scripts' literal-string `OPENPMD_ROOT` guards disappeared with the scripts. FINDINGS §7.2's "done as a follow-up" is contradicted by the branch content (M1) |
| wrappers "reproduce the old per-cluster behaviour" (FINDINGS §4, wrapper docstrings) | **no** | default run aborts at c-blosc2 (C1); FFTW3 invisible on rosi/delta, libpng/HDF5/FFTW3 invisible + ADIOS2 HDF5 provenance changed on perlmutter (M2); the `-DMPI_mpi_gnu_123_LIBRARY` MPI flags the old rosi/delta scripts passed are only commented-out examples in the new wrappers |
| "a failed build leaves no stamp and the script exits non-zero" (FINDINGS §6) | **refuted for boost** | reproduced: failing boost -> stamp written, rc 0 (C2); holds for the other 7 deps (they route through `deps_build`) |
| "byte-for-byte unchanged" generated scripts when disabled | yes | `diff -r` of two fully generated workflow trees (dev code via `PYTHONPATH` vs branch code, same venv, plain config): identical |
| "11 tests" in test_dependencies.py (FINDINGS §4) | no (trivial) | the file contains 13 test functions (n3) |
| "prefix built for a different key is detected and skipped" (README:73-76) | partially | true in cluster mode; unreachable in managed mode because targets are per-key - a different toolchain *rebuilds* everything and flips `current.env` (m6) |

## 5. Design discussion

The provider-abstraction choice (option d) is the right one for this codebase, and the report's central insight - that the build side is already provider-agnostic (`find_package` + `*_ROOT`/`CMAKE_PREFIX_PATH` hints, verified against `include/picongpu/CMakeLists.txt:40-47,116,184,331,414,483`) - is what makes the abstraction cheap. The two-mode design (cluster `*_ROOT` targets vs toolchain-keyed managed prefix + env file) correctly preserves the shared-cluster-install semantics of the old scripts, and the key design (cc/cxx/mpi/cmake/arch/versions) is sound; the MPI-present/absent distinction was verified to change the key.

The weaknesses are all at the seams the tests don't touch:

- **The provider loop is the trust boundary and it was never exercised with the full key set.** One typo (C1) and one missing rc-check (C2) break the primary path. A table-driven design (`DEPS_KEY -> (fn, version, root var, dirname)` plus a per-key function map, and a single `deps_build`-based execution path for *all* deps, including boost) would make this class of bug structurally impossible and would let a unit test stub the "build" and assert the loop's ordering/abort/summary behaviour for all 8 keys.
- **"Managed mode" was designed for the laptop (no profile at all); the clusters are the mixed case.** Every real profile exports *some* but not all `*_ROOT` vars, so the mixed case is not an edge case - it is the cluster case. The cleanest fix is to make the env file the *union* of cluster-mode hints (the profile's own `*_ROOT`) and managed-mode hints, and to make wrappers explicit about scope (`DEPS_ONLY` for perlmutter's module-provided deps, `DEPS_CMAKE_EXTRA_*` defaults for the MPI gnu_123 flags). Until the wrappers are validated on their clusters, the commit message/README should say "draft, not a drop-in replacement yet" rather than "replaces".
- **`current.env` as a mutable global pointer is the wrong stability primitive.** It works for one user/one toolchain (the tested case) and degrades to last-writer-wins otherwise (m6). Pinning the key in the generated scripts (build.sh recomputes the key after toolchain load and sources `<key>/picongpu-deps.env`) is a small change and removes an entire class of cross-toolchain breakage; it also makes the README's "skip with a warning" story true in managed mode.
- **Cache integrity** (M3/M4): for a shared, fetch-once cache, the fetch layer needs the same seriousness as the build layer - pinned checksums (the dependency table is static; a hash per dep is ~8 lines) and cache entries keyed by *what was requested* (tag), not just the name.
- **Alternatives considered:** building the provider table in Python and emitting per-dep makefiles/JSON would be more testable, but the shell-library approach is the right *draft* trade (no new runtime deps, mirrors the existing scripts' idiom, trivially debuggable on a cluster login node). Keep it; fix the seams.

## 6. Prioritized next steps

1. **Fix C1** (key->function map) and add a test that drives `deps_provider_source` over all 8 keys (stub builds) - then re-run a *full* local stack (boost + c-blosc2 + libpng + pngwriter + hdf5 + adios2 + openpmd + fftw3) to prove the default path end-to-end; the author's subset test skipped exactly the two deps that are broken.
2. **Fix C2**: route boost through `deps_build` (rc-checked, logged), stamp only on success; add the "failed build leaves no stamp" assertion as a test (fake failing source).
3. **Fix the profile drift (M1)** - rosi+delta `HDF5_VERSION=1.14.6`, delta `FFTW_ROOT` `$FFTW_VERSION`, plus the `FFTW_ROOT`->`FFTW3_ROOT` decision - or pin sane `DEPS_*_VERSION` defaults in the wrappers and correct FINDINGS §7.2.
4. **Close the mixed-mode gap (M2)**: write the env file whenever any managed-mode install happened (union of hints), fail fast otherwise; add `DEPS_ONLY` scoping + the MPICH `gnu_123` defaults to the perlmutter wrapper; state per-cluster deviations in the wrappers/README.
5. **Harden the cache (M3, M4)**: rc-check fetches, never `mv` a failed download, add per-dep sha256 pins; key git caches by tag (or verify the checkout tag on hit).
6. **Move the docs section** to `docs/source/install/dependencies.rst` with resolvable `literalinclude` paths (m9); correct FINDINGS §4 (11->13 tests; the pre-existing `dependencies.rst`).
7. Then, per the draft convention: validate the wrappers on rosi/delta/perlmutter (at least `--list` + dry `deps_guard` runs) and iterate on the `DEPS_CMAKE_EXTRA_*` values before treating the wrappers as drop-in.

## FYI (inherited from base, not scored here)

- The old per-cluster scripts share the `CXX=$(which CC)` defect (lookup of a literal binary "CC") that the new `picongpu-deps.sh:185` inherited (m2) - pre-existing, but the new script had a clean opportunity to do it right.
- `docs/source/install/dependencies.rst` (base) documents the manual dependency installs with per-library `cmake` snippets; the new section duplicates some of that content in the legacy root `INSTALL.rst` instead of extending the live page.
- The base `etc/picongpu/*/dependencies_autoinstall.sh` scripts had their own broken guards (`[ ! -d "OPENPMD_ROOT" ]` literal strings in rosi/perlmutter/delta, missing `$` in the delta FFTW path) - removed by this branch's replacement, which is the one genuine "drift fix" it contains.
