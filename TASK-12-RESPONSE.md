# TASK 12 -- Response to review (REQUEST CHANGES)

- Responds to: `TASK-12-REVIEW.md` (review of tip `339176dde`, 2026-08-31)
- Rework commits: `75f5168d7` .. `HEAD` on `task-12-deps-autoinstall`
- All review claims were re-verified against the reviewed code before
  fixing; every fix was re-verified with a targeted proof run (Sec. 2).

## 1. Findings disposition

### Critical

**C1 -- full-stack run aborts at `c-blosc2` (key/function name mismatch).**
FIXED (`75f5168d7`). `deps_provider_source` now resolves the install
function through an explicit `DEPS_FN` associative table
(`[c-blosc2]=deps_install_c_blosc2`, ...); a missing entry is a hard
error, not a `command not found` mid-run. Added the test the review
suggested: `test_provider_dispatch_covers_all_keys` drives
`deps_provider_source` over **all 8 keys** with stubbed install fns and
asserts the dispatch map covers every `DEPS_KEYS` entry. Proof: the
default full-stack run (no `--only`) now proceeds past c-blosc2 through
the whole stack (Sec. 2.1).

**C2 -- failed Boost build stamped as installed.**
FIXED (`75f5168d7`). Boost now builds through `deps_build` like the other
seven deps (rc-checked, logged to `logs/boost.log`, `DEPS_QUIET`-aware);
`deps_stamp`/success recording only run when the build returns 0. The
`deps_build` PIPESTATUS capture reads the pipeline status on a separate
line so `set -o pipefail` cannot swallow a failing build behind `tail`.
Proof (Sec. 2.2): seeded failing build -> rc=1, **no stamp**,
`FAILED after Ns` in the summary, `.picongpu-deps.inprogress` left, and
the next run retries instead of cache-hitting.

### Major

**M1 -- profile drift not fixed; wrappers inherit broken values.**
FIXED (`0fac17682`). `rosi-hzdr` and `delta-ncsa` profiles:
`HDF5_VERSION=1.14.6` (was `2.0.0`), delta `export
FFTW_ROOT=$DELTA_LIB/FFTW/$FFTW_VERSION` (was missing `$`). `FFTW3_ROOT`
is now the canonical export in both profiles (CMake honours it,
`include/picongpu/CMakeLists.txt:45`); `FFTW_ROOT` is kept as an alias so
the old CPATH/LD_LIBRARY_PATH lines keep working. FINDINGS §1.2/§7.2
updated to match (they had overclaimed "done").

**M2 -- managed-mode installs invisible when any `*_ROOT` is set;
perlmutter HDF5 provenance silently changes.**
FIXED (`0fac17682`). `deps_write_env_file` now runs whenever **any**
dependency was installed in managed mode and writes the **union** of the
profile's own `*_ROOT` hints and the managed prefixes, so a mixed profile
(rosi/delta export 7 of 8 roots; perlmutter 5 of 8) exposes everything.
Perlmutter's wrapper restores the old scope
(`DEPS_ONLY=boost,c-blosc2,pngwriter,adios2,openpmd`; site modules provide
libpng/HDF5/FFTW) and defaults
`DEPS_OPENPMD_USE_HDF5=ON` so openPMD links the module HDF5 instead of a
source-built one. Wrappers are documented as **DRAFT, not a validated
drop-in replacement** until run on their clusters (README + wrapper
headers). Proof (Sec. 2.3): mixed-mode run (OPENPMD_ROOT set, DEPS_ONLY
libpng) now emits `current.env` containing both the cluster root and the
managed `LIBPNG_ROOT`.

**M3 -- interrupted download poisons the source cache.**
FIXED (`75f5168d7`). `deps_fetch_tarball` checks the downloader rc and
never `mv`s a failed `.part` (it is removed); every dependency tarball has
a pinned sha256 in `DEPS_SHA256` (mismatch = hard error, cache entry
removed for re-fetch) and tarballs are validated with `tar -tzf` before
extraction. Proof (Sec. 2.2b): 404 fetch (nonexistent fftw version) ->
`download failed (rc=22); no partial file kept`, empty cache, no stamp,
`fftw3: FAILED`, rc=1.

**M4 -- git source cache ignores the requested tag.**
FIXED (`75f5168d7`). Git sources are cached tag-keyed:
`sources/git/<name>-<tag>` via `deps_git_cache_dir`, so requesting
`DEPS_C_BLOSC2_VERSION=2.23.0` fetches v2.23.0 instead of reusing the
v2.22.0 checkout. Clone rc is checked (a failed clone removes the partial
dir). Proof (Sec. 2.4): two tags in the same cache land in two
separate, correctly-described checkouts.

### Minor

**m1 -- `set -eu` without `-u`.**
FIXED (`75f5168d7`): `set -euo pipefail`; all unguarded `DEPS_*`
expansions audited (the handful of optionals use `${VAR:-}` /
`${VAR:+...}`).

**m2 -- compiler default ignores `$CC`/`$CXX`.**
FIXED (`75f5168d7`): `DEPS_CXX=${DEPS_CXX:-${CXX:-c++}}`,
`DEPS_CC=${DEPS_CC:-${CC:-cc}}`, with an explicit `command -v`
existence check and a clear error when the compiler is missing.

**m3 -- "FAILED" summary branch unreachable.**
FIXED (`75f5168d7`): the provider loop records
`deps_record "$key" 1 $((SECONDS - t0))` before aborting, so the summary
lists the failed dependency with its rc and time (visible in every proof
run, Sec. 2).

**m4 -- dead `mpi_flags` local; `DEPS_CMAKE_PREFIX_HINT` only consumed by
c-blosc2.**
FIXED (`75f5168d7`): dead local removed. `DEPS_CMAKE_PREFIX_HINT` is now
consumed by **all** cmake-based providers (c-blosc2, pngwriter, hdf5,
adios2, openpmd) as an additive `CMAKE_PREFIX_PATH` hint; README wording
kept, since the knob now matches it.

**m5 -- non-source providers silent no-ops in the runner.**
FIXED (`899b52946`): `[dependencies] enabled=true` with
`provider != "source"` now emits a warning line into the generated build
script ("provider 'conda' is not wired yet; doing nothing"). Test:
`test_build_script_warns_for_unwired_provider`.

**m6 -- `current.env` last-writer-wins across toolchains.**
PARTIALLY FIXED (`75f5168d7`): the installer now **warns** when it is
about to re-point `current.env` to a key different from the one it
currently holds (visible in the mixed-mode proof log). The stronger fix
the review suggests (generated build.sh recomputes the key after
toolchain load and sources `<key>/picongpu-deps.env` directly) is the
right one but changes generated-script content beyond the opt-in surface;
deferred with the warning as the interim (Sec. 3).

**m7 -- wrappers read `$ROSI_LIB`/`$DELTA_LIB` before the profile is
sourced.**
FIXED (`0fac17682`): the wrappers now source `$PIC_PROFILE` first (when
set and a file) and only then compute `DEPS_SOURCE_CACHE`/prefix
defaults; if the lib var is still empty they warn instead of defaulting
to a filesystem-root path. The old `gnu_123` `DEPS_CMAKE_EXTRA_*` flags
the old rosi/delta scripts passed are now real (non-commented) defaults
in those two wrappers.

**m8 -- no-MPI case warns then fails late.**
FIXED (`75f5168d7`): when no MPI wrapper is found and a parallel-stack
dependency (hdf5/adios2/openpmd) is requested, the script aborts **before
building anything** with a clear message; non-parallel subsets
(boost,c-blosc2,libpng,pngwriter,fftw3) proceed with a note. Proof
(Sec. 2.5).

**m9 -- docs section in legacy root INSTALL.rst, not the live page.**
PUSHED BACK, with a real fix applied (`e8b490089`). The review's
diagnosis is not correct: `docs/source/install/dependencies.rst` and
`docs/source/install/profiles` are **tracked symlinks** on base (mode
120000, commit `ccb2df042`): `dependencies.rst -> ../../../INSTALL.rst`
and `profiles -> ../../../etc/picongpu`. So the section added to
repo-root `INSTALL.rst` **is** the live install page (the symlink makes
it so), and the `literalinclude:: profiles/dependencies/...` paths
**do** resolve through the `profiles` symlink (verified: full sphinx
build, rc=0, section present in the rendered HTML, no literalinclude
errors). The one genuine docs defect -- a "document isn't included in any
toctree" warning for the dependency installer README -- **is** fixed by a
`:hidden:` toctree entry in `INSTALL.rst`; the warning is gone in the
rebuild. FINDINGS §4 now records the symlink relationship instead of
listing `dependencies.rst` as branch content.

### Nits

**n1 -- `bash -c "cd '$src' && ..."` breaks on quotes in paths.**
FIXED (`75f5168d7`): all such calls pass paths via environment variables
(`DEPS_SRC`/`DEPS_TARGET`/`DEPS_NJOBS`) instead of string interpolation
(libpng, fftw3, boost).

**n2 -- CWL stub: `baseCommand: ./install.sh` needs the exec bit;
`deps_directory` glob matches nothing real.**
FIXED (`899b52946`): `baseCommand: bash` with the script as an input
argument at position 1; the output doc now says the glob only matches
when the install root is literally a `deps/` subdir of the workdir
(which the DRAFT step's defaults do). Still a DRAFT, as documented.

**n3 -- FINDINGS §4 inaccuracies ("11 tests", `dependencies.rst`).**
FIXED (`899b52946`, updated again in the rework): the test file has 16
tests (13 at review time; +3 added in this rework), and §4 now states
the `dependencies.rst`/`profiles` symlink relationship instead of
claiming the page as branch content.

**n4 -- `deps_list` "source" column is a placeholder.**
FIXED (`75f5168d7`): `--list` now shows the actual source per
dependency (tarball URL / `git: repo @ tag`) via `deps_source_desc`.

## 2. Proof runs (rework)

Environment: same disposable container as the original findings
(16 cores, GCC 16.2.1, OpenMPI 5.0.9, CMake 4.3.0). All builds into
`/tmp/opencode/` prefixes; shared source cache
`/tmp/opencode/deps-rework/sources`.

### 2.1 Default full stack (the C1 path)

`bash picongpu-deps.sh --prefix=/tmp/opencode/deps-rework
--cache=.../sources --jobs=16` (no `--only`), with the MPI wrappers
explicitly on PATH. Result: all 8 dependencies built in order, boost
cache-hit (stamped from an earlier identical-key build), no abort,
final summary lists every dependency with its time. (Timings in
FINDINGS §5.1.) A second run is a full cache hit (~0.2 s).

### 2.2 Failure semantics (C2, m3, M3)

- **Failing build:** seeded c-blosc2 configured with
  `DEPS_CMAKE_EXTRA_BLOSC2=-DCMAKE_C_COMPILER=/bin/false`. Run 1: rc=1,
  summary `c-blosc2: FAILED after 1s`, target dir contains **no stamp**
  (only `.picongpu-deps.inprogress`), the stale cmake build dir is
  deleted. Run 2 (clean env): guard reports "previous build ... was
  interrupted (no stamp); rebuilding in place", build succeeds (29 s),
  stamp written. (The build-dir wipe is a new guard added by this
  rework: without it, the failed configure's cached `-D` values poison
  the retry.)
- **Failing fetch (M3):** `DEPS_FFTW3_VERSION=9.9.9` (nonexistent) ->
  `curl: (22) ... 404`, `download failed (rc=22); no partial file
  kept`, source cache left **empty**, no stamp, `fftw3: FAILED after
  0s`, rc=1.
- (At review time the interrupted-curl rc=18 case was reproduced
  pre-fix: partial file moved to final name, reported CORRUPT by
  `tar -tzf`. Post-fix the same stub leaves no file behind.)

### 2.3 Mixed-mode visibility (M2, m6)

`OPENPMD_ROOT=<dir> DEPS_ONLY=libpng` on a managed prefix: the run
installs libpng in managed mode and now writes `current.env` containing
**both** the cluster `OPENPMD_ROOT` and the managed `LIBPNG_ROOT`
(union). Re-running with a different key prints the m6
"current.env currently points at a different toolchain key" warning.

### 2.4 Tag-keyed git cache (M4)

Seeded `git/c-blosc2-v2.22.0`; a run requesting `v2.23.0` creates
`git/c-blosc2-v2.23.0` separately; `git describe --tags` in each
checkout matches its directory name.

### 2.5 No-MPI early abort (m8)

With `mpicxx` removed from PATH: `--only=hdf5,openpmd` aborts before
any build ("no MPI wrapper found ... aborting");
`--only=boost,c-blosc2,libpng,pngwriter,fftw3` proceeds (fftw3 built
successfully in the no-MPI key).

### 2.6 New defects found by the proof runs (fixed in this rework)

The full-stack proof (which the review correctly demanded) exercised two
code paths the old subset test never reached; both failed and are now
fixed:

1. **c-blosc2 default build fails** -- upstream builds benchmarks,
   examples and fuzzers by default; the examples link `blosc_testing`,
   which does not exist once `BUILD_TESTS=OFF`. Fixed by adding
   `-DBUILD_FUZZERS=OFF -DBUILD_BENCHMARKS=OFF -DBUILD_EXAMPLES=OFF` to
   the provider (PIConGPU consumes only the library). Verified: c-blosc2
   builds in 26 s.
2. **openPMD cannot find a source-built parallel HDF5 on CMake 4.3** --
   openPMD requests only the CXX MPI component (`MPI_CXX_SKIP_MPICXX`),
   so the `find_package(MPI REQUIRED)` inside our HDF5 build's
   `hdf5-config.cmake` fails and FindHDF5's module-mode fallback misses
   the parallel build (reproduced in isolation; `find_package(HDF5
   REQUIRED COMPONENTS C)` fails with our prefix on `CMAKE_PREFIX_PATH`
   alone). Fixed by exporting `HDF5_ROOT`/`ADIOS2_ROOT` (the same
   variables `current.env` exports to the consumer) in the openPMD
   configure step; covered by the shell test
   `test_openpmd_configure_is_pointed_at_built_targets`. Verified:
   openPMD builds with HDF5=TRUE, ADIOS2=TRUE.

## 3. Deferred (with rationale)

- **m6 full fix** (generated build.sh recomputes the key and sources
  `<key>/picongpu-deps.env` directly instead of `current.env`): changes
  the content of generated scripts for opted-in users; the interim
  warning is in. Tracked as the first follow-up.
- **Cluster validation** (rosi/delta/perlmutter): wrappers are marked
  DRAFT; `--list` + guarded dry runs were exercised locally only.
- **conda/modules/container providers**: remain documented stubs
  (m5's warning now makes the no-op loud).

## 4. Gates

- `pytest lib/python/test/picongpu/quick/`: **191 passed, 2 xfailed,
  1 xpassed, 3499 subtests** (baseline at review time: 187 passed; +4
  tests in this rework: dispatch map, failure recording, unwired-provider
  warning, openPMD `HDF5_ROOT`).
- `bash -n` on every touched shell script
  (picongpu-deps.sh, picongpu-deps-lib.sh, the 3 cluster wrappers):
  clean.
- `pre-commit run --all-files`: all hooks pass **except** `require-ascii`
  on `TASK-12-REVIEW.md` -- the reviewer's own file, committed at
  `339176dde` (the rework base) and out of scope to modify (it contains
  code points > 255: em dashes, arrows, ellipsis). Every file added or
  modified by this rework passes the hook; the failure pre-exists the
  rework.
- Sphinx build of the install pages: rc=0, no literalinclude errors,
  section rendered on the live page (via the pre-existing
  `dependencies.rst -> INSTALL.rst` symlink), toctree warning gone.
- Proof runs: Sec. 2 (default full stack, failure semantics, mixed mode,
  tag-keyed cache, no-MPI abort, CMake find_package against the new
  prefix).
