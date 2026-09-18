# TASK 12 -- Findings: general, portable installation of compiled build dependencies

Status: **draft for iteration** (exploratory task), reworked 2026-08-31
Branch: `task-12-deps-autoinstall` - Base: `dev` @ b4e4ca5b2
Date: 2026-08-29 (rework: 2026-08-31, see `TASK-12-RESPONSE.md`)

## TL;DR

- **Feasible in general, with one hard gap and a few per-cluster caveats.**
  A single parameterised installer can cover *every* cluster where a
  compiler, CMake and (for the parallel stack) MPI wrappers are available --
  i.e. everywhere PIConGPU itself can be compiled. What is **undoable** in
  general: (1) **PNGwriter is not on conda-forge** (404 checked 2026-08-29),
  so no *prebuilt* provider covers the full stack; (2) a single prebuilt
  prefix is **not portable across toolchains** -- only "build against the
  loaded toolchain" or "run a container" is; (3) on systems with **no
  compiler at all** (e.g. pure login nodes without toolchain modules,
  container-only sites) even the `source` provider fails -- only `modules`,
  `conda` or `container` can work there.
- **Recommendation (implemented as draft):** option **(d) provider
  abstraction** (`provider: source | conda | modules | container` in
  `picongpurc.toml`), with **(a) the generalised script** and **(b) opt-in
  workflow/runner wiring** implemented, and **(c) prebuilt providers**
  documented (conda available for 7 of 8 dependencies; PNGwriter always
  from source).
- **Proven locally (subset):** FFTW3 + libpng + PNGwriter + parallel HDF5 +
  openPMD-api (HDF5+MPI, no ADIOS2) built by the parameterised script in
  **~3 min on 16 cores**, a second run in **0.2 s** (cache hit), and a
  scratch CMake project using the *same find_package calls as PIConGPU*
  found all of them via the generated `CMAKE_PREFIX_PATH`/`*_ROOT`/
  `PKG_CONFIG_PATH` hints.

---

## 1. Inventory: what exists today

### 1.1 How the build consumes dependencies (the contract a provider must fulfil)

All consumption happens in CMake with plain `find_package` + env-var hints
(`include/picongpu/CMakeLists.txt`):

| dependency | CMake call | hints honoured | mandatory? |
|---|---|---|---|
| Boost >= 1.74 (program_options) | `find_package(Boost 1.74.0 REQUIRED CONFIG COMPONENTS program_options)` (line 184; also `PMaccConfig.cmake:297`) | `BOOST_ROOT` env appended to `CMAKE_PREFIX_PATH` (line 42); profiles point at `$BOOST_ROOT/lib/cmake` (b2 install layout) | **yes (REQUIRED)** |
| openPMD >= 0.15 | `find_package(openPMD 0.15 CONFIG COMPONENTS MPI)` (line 331) | `OPENPMD_ROOT` env (line 44) | optional (AUTO); plugin only if `openPMD_HAVE_ADIOS2 OR openPMD_HAVE_HDF5` |
| PNGwriter >= 0.7.0 | `find_package(PNGwriter 0.7.0 CONFIG)` (line 414) | `PNGwriter_ROOT` via CMP0144 (`cmake_policy(VERSION 3.28.0)`, line 116) **and** `$CMAKE_PREFIX_PATH` (line 47; profiles prepend it) | optional (AUTO) |
| FFTW3 | `pkg_check_modules(FFTW3 fftw3 IMPORTED_TARGET)` (lines 483-485) | pkg-config; `FFTW3_ROOT` env appended to `CMAKE_PREFIX_PATH` (line 45) -- CMake's `FindPkgConfig` searches `<prefix>/{,64}lib/pkgconfig` of each `CMAKE_PREFIX_PATH` entry | optional (AUTO, Shadowgraphy) |
| HDF5 / ADIOS2 / c-blosc2 | *not found directly by PIConGPU* -- by openPMD's/ADIOS2's own config files | `HDF5_ROOT`, `ADIOS2_ROOT`, `BLOSC_ROOT` + `CMAKE_PREFIX_PATH` | transitive |
| ISAAC >= 1.4 | `find_package(ISAAC 1.4.0 CONFIG QUIET)` | `ISAAC_DIR`/`CMAKE_PREFIX_PATH` | optional (out of scope) |

**Consequence: the build needs no special machinery.** Any provider that
produces prefixes exposing the CMake package config files (and, for FFTW3,
a `fftw3.pc` discoverable via `CMAKE_PREFIX_PATH`/pkg-config) plugs in.
The task is purely *producing* such prefixes portably.

### 1.2 The duplicated per-cluster scripts

`etc/picongpu/{rosi-hzdr,delta-ncsa,perlmutter-nersc}/dependencies_autoinstall.sh`
(+ spack-based `bash-devServer-hzdr/*_install.sh`):

**Common core (~95% identical):** source `$PIC_PROFILE`; for each of Boost,
c-blosc2, libpng, PNGwriter, HDF5 (parallel), ADIOS2 (MPI+HDF5), openPMD
(HDF5+ADIOS2), FFTW: `if [ ! -d "$<NAME>_ROOT" ]` -> fetch source ->
build -> install into `$<NAME>_ROOT`; parallel `-j 16`.

**Per-cluster deltas (this defines the parameterisation):**

| delta | rosi-hzdr | delta-ncsa | perlmutter-nersc |
|---|---|---|---|
| source dir | `/bigdata/.../lib_buildDir` (shared FS) | `$HOME/...` | `$CFS/$proj/$USER/lib_run_tmp` (scratch) |
| MPI | OpenMPI (`OMPI_DIR` from `mpiexec`) | OpenMPI (`OMPI_DIR` from `mpicxx`) | **MPICH** (`MPICH_DIR`) |
| ADIOS2 quirks | `-DMPI_mpi_gnu_123_LIBRARY=...` | same | `sed` patch of `DetectOptions.cmake` (client/server) + same `-DMPI_*` flags |
| PNGwriter CMake | **`CMAKE_POLICY_VERSION_MINIMUM=3.5`** (loads cmake 4.0.3) | plain | plain |
| version drift | ADIOS2 2.11.0, openPMD 0.17.0 | same | ADIOS2 **2.10.2**, openPMD **0.17.1** |
| missing steps | -- | -- | **no libpng, no HDF5, no FFTW** (modules provide) |

**Drift/bugs found during the diff** (evidence that unmanaged copies
deteriorate -- the case for a single source of truth). All five were
addressed in the rework (2026-08-31): the three profile bugs are fixed in
the profiles themselves, the literal-string guards disappeared with the
old scripts, and the shared script applies the PNGwriter CMake-policy
workaround for every cluster:

- rosi: `HDF5_VERSION=2.0.0` in the profile (`#1.14.6` commented) -> the
  script would `wget` a non-existent `hdf5_2.0.0` tag -> broken.
- rosi: guards written as `if [ ! -d "OPENPMD_ROOT" ]` / `"FFTW_ROOT"`
  (missing `$`) -> check a literal directory in the CWD -> guard never hits.
- delta profile: `export FFTW_ROOT=$DELTA_LIB/FFTW/FFTW_VERSION` (missing
  `$`).
- rosi/delta profiles export `FFTW_ROOT`, while CMake honours
  `FFTW3_ROOT` (works only via the `CMAKE_PREFIX_PATH` line).
- delta's PNGwriter has no CMake policy workaround: it would break if
  delta's CMake is ever updated to >= 3.27 -- the toolchain version, not the
  cluster, determines the requirement.

## 2. Feasibility analysis -- "is this undoable, and where?"

### 2.1 Constraints

1. **No root on most clusters** -> only user-owned prefixes are universal.
   Source builds satisfy this; so do conda envs and containers (user-mode
   `apptainer`). yes no blocker.
2. **Toolchain heterogeneity** (GCC versions, OpenMPI vs MPICH, CUDA/HIP,
   CMake 3.x vs 4.x) -> binaries are not interchangeable; a *single
   prebuilt prefix is not portable*. Portable options are exactly:
   (a) build from source against the loaded toolchain, (b) a prebuilt
   provider that is itself toolchain-consistent per site (conda-forge pins
   its own compiler), or (c) a container that ships its whole toolchain.
   The measured PNGwriter case (needs `CMAKE_POLICY_VERSION_MINIMUM=3.5`
   on CMake >= 3.27, not on older) is a concrete example: the *same*
   dependency needs different flags per toolchain version.
3. **Build time** -> full stack (Boost + parallel HDF5 + ADIOS2 + openPMD)
   ~ 10-30+ min: unacceptable per run. A **shared, toolchain-keyed cache**
   is mandatory. Measured subset (no Boost/ADIOS2) on 16 cores:
   ~3 min cold, ~0.2 s warm (Sec. 5).
4. **Network restrictions / login vs compute** -> fetch sources once (login
   node) into a shared cache; compute nodes can then run `--offline`.
5. **Upstream gaps** -> PNGwriter 0.7.0 is unmaintained-ish:
   `cmake_minimum_required(VERSION 3.0.1)` (hard-rejected by CMake >= 3.27
   without the policy workaround), needs libpng. Version pinning must live
   in configuration, not script text.
6. **Where no provider works** (the precise "undoable" answer):
   - **PNGwriter is not on conda-forge** (checked via the anaconda.org API,
     2026-08-29: `conda-forge/pngwriter` -> HTTP 404). So `provider: conda`
     alone can never deliver the full stack; PNGwriter must be built from
     source (spack does have it, but spack is not universally available).
   - **No compiler anywhere on the node/site** (and no container runtime,
     no modules): nothing works except a pre-built, pre-matched prefix
     carried from elsewhere -- fragile and out of scope. This is the only
     truly "undoable" case; in practice PIConGPU cannot be *compiled*
     there either, so the dependency problem is moot.
   - **Binary incompatibility traps** (undoable *by accident* without
     keying): e.g. an openPMD built with OpenMPI 5 used under MPICH, or a
     Boost built with GCC 13 used with a GCC 16 frontend. The cache key
     (Sec. 7) is the mitigation; it cannot make incompatible toolchains
     compatible -- it only refuses to mix them.
   - **HDF5 2.x / new CMake combinations** may need per-version flags
     (escape hatches `DEPS_CMAKE_EXTRA_*` exist for this).

### 2.2 conda-forge availability (checked 2026-08-29, anaconda.org API)

| package | on conda-forge | latest |
|---|---|---|
| boost | yes | 1.85.0 |
| c-blosc2 | yes | 3.3.2 |
| hdf5 | yes | 2.2.0 |
| adios2 | yes | 2.12.1 |
| openpmd-api | yes | 0.17.1 |
| fftw | yes | 3.3.11 |
| libpng | yes | 1.6.58 |
| **pngwriter** | no **404** | -- |

So the conda provider covers 7 of 8 and is a legitimate *fallback* for
sites without compilers on login nodes; the 8th (PNGwriter) is always a
source build (fast: 4 s in our measurement).

## 3. Solution space

| option | what | pros | cons |
|---|---|---|---|
| **(a) generalised autoinstall script** | one shared script parameterised from profile/preset (versions, prefixes, cores, MPI wrappers), replacing the 3+1 duplicates | portable = "works anywhere you can compile"; keeps today's guarantees; idempotent shared installs; no new runtime dependencies; fixes the drift/bugs of Sec. 1.2 | still needs a toolchain; build time first run; per-cluster quirks need escape hatches |
| **(b) workflow integration** | CWL step / runner hook before `build_step` producing the prefix + `CMAKE_PREFIX_PATH` for the build | "PICMI script + picongpurc.toml handles everything" extends to dependencies; idempotent -> cheap on repeat runs; cache shared between workflow runs | coupling to the CWL graph must stay opt-in (default behaviour unchanged); runtime env for the *submitted* job also needs the prefixes |
| **(c) prebuilt providers** | conda-forge env (7/8 deps) / full-stack container image (SIF) / modules | no local compilation; fastest where the provider runs; container = full toolchain consistency (connects with task 11 EFP path) | PNGwriter gap (conda); containers need a runtime (apptainer/singularity) and site images; conda env must match the site's MPI for the parallel stack, otherwise openPMD/ADIOS2 built against conda's MPI must *be* the MPI used at run time |
| **(d) provider abstraction** | a `provider: source \| conda \| modules \| container` setting per preset/`picongpurc.toml`; any provider that fills the `*_ROOT`/`CMAKE_PREFIX_PATH` contract (Sec. 1.1) plugs into the unchanged build | "general" in the requested sense: one configuration surface, per-site choice; (a)+(b) implement `source`, (c) adds the rest later; the *boundary* is explicit: the provider never manages the toolchain (compiler/CUDA) -- modules/presets own that | more moving parts (the abstraction itself); each non-source provider needs its own validation story |

**Recommendation: (d), with (a)+(b) implemented and (c) documented** -- as
sketched by the task. Rationale: the build-side contract is already
provider-agnostic (Sec. 1.1), so the abstraction is cheap; (a) is the only
universally portable *mechanism*, (b) makes it part of the PICMI flow,
and (c) is documented as a fallback with the PNGwriter gap explicitly
called out. The alternative "just generalise the scripts" ((a) alone)
leaves the manual before-step and loses the PICMI "one config file" story.

## 4. What was drafted (this branch)

```
etc/picongpu/dependencies/
  picongpu-deps.sh        # entry point (exec or source): --help/--list/--only/--jobs/
                          #   --prefix/--cache/--force/--offline/--quiet/--provider
  picongpu-deps-lib.sh    # dependency table, toolchain-keyed cache, fetch-once,
                          #   per-dep build fns, stamps, env-file generation, providers
  README.md               # usage, variable reference, cache layout, limitations
etc/picongpu/{rosi-hzdr,delta-ncsa,perlmutter-nersc}/dependencies_autoinstall.sh
                          # now thin wrappers (cluster settings + exec shared script)
lib/python/picongpu/dependencies.py            # [dependencies] config -> DEPS_* env
lib/python/picongpu/pypicongpu/runner.py       # opt-in wiring into build/prepare/submit scripts
lib/python/picongpu/templates/workflow/steps/install_dependencies.cwl  # DRAFT CWL step (not wired)
lib/python/test/picongpu/quick/test_dependencies.py                       # 16 tests
CHANGELOG.md
NOTE: docs/source/install/dependencies.rst and docs/source/install/profiles
PRE-EXIST on base (commit ccb2df042) as symlinks to repo-root INSTALL.rst
and etc/picongpu respectively; the dependency-install section therefore
lives in INSTALL.rst and appears on the live install page via the symlink
(the "Automatic Installation of Dependencies" section).
```

Design decisions:

- **Two target modes.** *Cluster mode*: the profile already exports
  `<dep>_ROOT` -> install into those prefixes (old behaviour, shared
  cluster FS installs preserved). *Managed mode* (laptop/CWL, no
  profile): install into `<DEPS_INSTALL_ROOT>/<toolchain-key>/<name>-<version>`
  and generate `picongpu-deps.env` + a stable `current.env` that the
  generated build/run scripts source.
- **Wrapper choice (documented per task):** the 3 per-cluster scripts
  become thin wrappers that `exec` the shared script -- one source of
  truth, per-cluster overrides stay possible via `DEPS_*` variables
  (e.g. `DEPS_ADIOS2_PATCH_CLIENT_SERVER=1` for perlmutter's MPICH,
  `DEPS_CMAKE_EXTRA_ADIOS2` for the old `-DMPI_mpi_gnu_123_LIBRARY` hack,
  cluster-shared `DEPS_SOURCE_CACHE`). The spack-based
  `bash-devServer-hzdr` installers are untouched (a different provider:
  they document `provider: spack` as a natural 5th value).
- **Runner wiring (opt-in, default-off).** `[dependencies].enabled = true`
  in `picongpurc.toml` makes the *generated* `build.sh` run the installer
  before `pic-build` and all of build/prepare-submission/submit source
  `current.env`. With the flag off, generated scripts are byte-for-byte
  unchanged (tested). The standalone CWL step is a clearly marked DRAFT:
  wiring a conditional step into `workflow.cwl` would change every
  existing workflow's graph (and RO-Crate), so the working path is the
  build-script hook; the CWL file is the future integration point.
- **PNGwriter workaround kept** (`-DCMAKE_POLICY_VERSION_MINIMUM=3.5`),
  now justified by evidence (Sec. 2.1.5) and a no-op for older CMake.

## 5. Local subset test (required end-to-end proof)

Environment: disposable Fedora 44 container, 16 cores, GCC 16.2.1,
OpenMPI 5.0.9, CMake 4.3.0. Install root `/tmp/opencode/deps-prefix`,
`DEPS_JOBS=16`, `DEPS_ONLY=fftw3,libpng,pngwriter,hdf5,openpmd`
(Boost + ADIOS2 + c-blosc2 intentionally skipped per task constraints).

**Cold build (sequential, includes source fetch):**

| dependency | version | time |
|---|---|---|
| libpng | 1.6.34 | 10 s |
| pngwriter | 0.7.0 | 4 s |
| hdf5 (parallel, MPI) | 1.14.6 | 65 s |
| openpmd-api (HDF5+MPI, no ADIOS2) | 0.17.1 | 64 s |
| fftw3 | 3.3.10 | 32 s |
| **total** | | **~ 175 s** |

**Warm run (cache hit): 0.175 s.** `DEPS_OFFLINE=1` with warm cache works
(no network). A run under a *different* toolchain key correctly warns
"built for a different toolchain ... skipping".

**CMake side** -- a scratch project replicating PIConGPU's exact calls
(`find_package(PNGwriter 0.7.0 CONFIG)`, `find_package(openPMD 0.15 CONFIG
COMPONENTS MPI)`, `pkg_check_modules(FFTW3 fftw3)`, `cmake_policy(VERSION
3.28.0)` for CMP0144) with only the generated `current.env` sourced:

```
-- Found PNGwriter: .../pngwriter-0.7.0/lib/cmake/PNGwriter
-- Found MPI: TRUE (found version "3.1")
-- Found openPMD: .../openpmd-api-0.17.1/lib64/cmake/openPMD (HDF5=TRUE, ADIOS2=FALSE)
-- Found FFTW3: 3.3.10 (.../fftw3-3.3.10/lib)
```

All found via the same hints PIConGPU honours (`CMAKE_PREFIX_PATH`,
`*_ROOT`, `PKG_CONFIG_PATH`). Caveat observed: the *consumer* also needs
the MPI wrappers on PATH (openPMD's `COMPONENTS MPI` re-detects MPI) --
exactly as on clusters where the profile loads the MPI module.

### 5.1 Full-stack proof (rework, 2026-08-31)

The default invocation (no `--only`) -- the path that was broken at review
time (C1) -- now builds the entire stack end-to-end on the same container
(16 cores, GCC 16.2.1, OpenMPI 5.0.9, CMake 4.3.0), sources pre-seeded in
the shared cache:

| dependency | version | cold time |
|---|---|---|
| boost | 1.87.0 | 117 s |
| c-blosc2 | 2.22.0 | 26 s |
| libpng | 1.6.34 | 7 s |
| pngwriter | 0.7.0 | 4 s |
| hdf5 (parallel, MPI) | 1.14.6 | 66 s |
| adios2 (MPI + HDF5) | 2.11.0 | 134 s |
| openpmd-api (HDF5 + ADIOS2 + MPI) | 0.17.1 | 48 s |
| fftw3 | 3.3.10 | 28 s |
| **total** | | **~ 430 s (~ 7 min)** |

Two real defects were found and fixed by this proof run, neither reachable
by the old subset test:

- **c-blosc2 builds its benchmarks/examples/fuzzers by default** (and the
  examples link `blosc_testing`, which does not exist when
  `BUILD_TESTS=OFF`) -- the default run failed after the core library was
  built. The provider now passes
  `-DBUILD_FUZZERS=OFF -DBUILD_BENCHMARKS=OFF -DBUILD_EXAMPLES=OFF`
  (PIConGPU consumes only the library).
- **openPMD cannot find a source-built parallel HDF5 on recent CMake
  (4.3)**: openPMD requests only the CXX MPI component
  (`MPI_CXX_SKIP_MPICXX`), so the `find_package(MPI REQUIRED)` inside our
  HDF5 build's `hdf5-config.cmake` fails, and FindHDF5's module-mode
  fallback misses the parallel build. The openPMD provider now exports
  `HDF5_ROOT`/`ADIOS2_ROOT` (the same variables `current.env` hands to
  the consumer) for its configure step; a shell test asserts this.

A second run of the completed prefix is a full cache hit: **0.179 s**,
8 x "already installed (cache hit, skipping)".

The scratch CMake project of Sec. 5 was extended with the remaining
find_package calls (Boost 1.74 CONFIG program_options, Blosc2, ADIOS2) and
re-run against this prefix's `current.env` only -- all found, and openPMD
now reports **HDF5=TRUE, ADIOS2=TRUE**:

```
-- Found Boost: 1.87.0 (.../boost-1.87.0/lib/cmake/Boost-1.87.0)
-- Found Blosc2: 2.22.0 (.../c-blosc2-2.22.0/lib64/cmake/Blosc2)
-- Found ADIOS2: 2.11.0 (.../adios2-2.11.0/lib64/cmake/adios2) [C CXX MPI]
-- Found PNGwriter: .../pngwriter-0.7.0/lib/cmake/PNGwriter
-- Found openPMD: .../openpmd-api-0.17.1/lib64/cmake/openPMD (HDF5=TRUE, ADIOS2=TRUE)
-- Found FFTW3: 3.3.10 (.../fftw3-3.3.10/lib)
```

(The Sec. 5 "10-30 min" extrapolation for the full stack was therefore
conservative: measured ~7 min on 16 cores, dominated by ADIOS2.)

## 6. Cache-keying design

- **Key** = sha256 of (C compiler version line, C++ compiler version line,
  MPI wrapper version line, CMake version line, `uname -m`, all resolved
  dependency versions), truncated to 12 hex chars + arch suffix.
  Deterministic: identical key across repeated runs on the same
  toolchain (verified); different key when MPI is absent vs present
  (verified) -> the parallel and non-parallel stacks never mix.
- **Layout:** shared `sources/` (fetch-once, key-independent) +
  `<key>/{src,build,logs,<name>-<version>,fingerprint.txt,picongpu-deps.env}`
  + stable `current.env` pointer (Sec. 4). Git sources are cached
  **tag-keyed** (`sources/git/<name>-<tag>`) so a `DEPS_<NAME>_VERSION`
  override always fetches the requested tag, never a stale checkout of
  another version. Tarball sources are pinned by sha256
  (`DEPS_SHA256` table; a mismatch is a hard error and the cache entry is
  removed for re-fetch) and validated with `tar -tzf` before use, so an
  interrupted download can never be mistaken for a cache hit.
- **Guards:** per-dep `.picongpu-deps.stamp` (key, dep, date, version,
  compiler); existing dir with matching stamp -> skip; existing dir with
  *foreign* stamp -> warn + skip (`DEPS_FORCE=1` to rebuild); existing dir
  without stamp (legacy per-cluster install) -> skip; empty dir
  (failed previous run) -> rebuild in place. A build in flight writes a
  `.picongpu-deps.inprogress` marker first; `deps_stamp` removes it on
  success. An interrupted/failed run therefore leaves a dir that is
  *retried* on the next run, never mistaken for installed.
- **Failure semantics:** a failed build leaves no stamp, records
  `FAILED` in the summary, and the script exits non-zero (aborts the
  workflow step before `pic-build`). A failed cmake *configure* also
  deletes the out-of-tree build dir so the cached `-D` values of the
  failed configure cannot poison the retry (verified: poisoned
  `CMAKE_C_COMPILER` configure -> retry from clean slate -> success).
- **Env file (managed mode):** written whenever **any** dependency was
  installed in managed mode, as the **union** of the profile's own
  `*_ROOT` hints and the managed prefixes; the old "only when all eight
  roots are unset" condition silently dropped mixed-profile installs
  (rosi/delta/perlmutter are all mixed). A `current.env` whose key differs
  from the new one is warned about before being re-pointed.

## 7. Open items for the requester

1. **Cluster validation on real systems** (rosi/delta/perlmutter): the
   draft targets their `*_ROOT` layouts but has only been exercised
   locally. Per-cluster `DEPS_CMAKE_EXTRA_*` values (e.g. the
   `-DMPI_mpi_gnu_123_LIBRARY` flag) need confirmation against each
   cluster's current MPI.
2. **Fix the profile drift found in Sec. 1.2** (rosi/delta
   `HDF5_VERSION=2.0.0`, delta `FFTW_VERSION` typo, `FFTW_ROOT` vs
   `FFTW3_ROOT`) -- **DONE in the rework (2026-08-31)**: profiles now say
   `HDF5_VERSION=1.14.6`, the delta typo is fixed, and `FFTW3_ROOT` is the
   canonical export (kept `FFTW_ROOT` as an alias for the old scripts'
   CPATH/LD_LIBRARY_PATH lines).
3. **Decision:** keep the per-cluster wrappers (chosen) vs. delete them
   once all presets are migrated to `[dependencies]` in
   `picongpurc.toml`.
4. **CWL step wiring** (`install_dependencies.cwl` is a DRAFT stub):
   decide whether to add a conditional step to `workflow.cwl` (changes
   every workflow's graph/RO-Crate) or keep the build-script hook as the
   integration point (chosen for the draft).
5. **conda provider hardening** (draft): env generation from a
   `environment.yml`, and the policy for the parallel stack (conda's own
   MPI vs the site's MPI). PNGwriter stays a source build either way.
6. **container provider** (stub): build the full-stack SIF (connects with
   task 11) and the apptainer invocation.
7. **Boost `lib/cmake` assumption**: the env file assumes the b2 install
   layout (`$BOOST_ROOT/lib/cmake`), as all existing profiles do; a
   CMake-built Boost would need `lib64`/variant handling.
8. **`FFTW_ROOT` compat**: the generated env exports both `FFTW3_ROOT`
   (CMake hint) and `FFTW_ROOT` (profile compat); profiles could migrate
   to `FFTW3_ROOT`.

## 8. Risks

- **Draft quality**: the shared script has only been tested on one
  toolchain (GCC 16/OpenMPI 5/CMake 4.3). The per-cluster escape hatches
  exist precisely because other combinations (old GCC, MPICH, CMake 3.x,
  CUDA) may need adjustments; expect iteration on real clusters.
- **DEPS_FORCE on shared prefixes** deletes an existing `*_ROOT`
  directory (rm -rf) -- deliberate (matches "rebuild") but dangerous on
  shared storage; the default (no force) never deletes.
- **Generated build.sh grows** when enabled; the CWL build step runs it
  on the build host, so first-run build time increases by up to ~30 min
  for a cold full stack (one-time per toolchain key, then ~0.2 s).
- **Runtime env assumption**: the run/submit scripts source
  `current.env` from a path valid on the same filesystem as the build
  (standard for the tbg flow); multi-fs setups need `prefix` set to a
  shared location.
