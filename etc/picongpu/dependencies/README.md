# PIConGPU dependency installation (DRAFT)

Shared, parameterised installation of the **compiled C++ dependencies** of
PIConGPU:

| key        | default version | exposed as     | found by PIConGPU via                        |
|------------|-----------------|----------------|----------------------------------------------|
| `boost`    | 1.87.0          | `BOOST_ROOT`   | `find_package(Boost 1.74 REQUIRED CONFIG)`   |
| `c-blosc2` | 2.22.0          | `BLOSC_ROOT`   | (transitively by ADIOS2/openPMD)             |
| `libpng`   | 1.6.34          | `LIBPNG_ROOT`  | (required by PNGwriter)                      |
| `pngwriter`| 0.7.0           | `PNGwriter_ROOT` | `find_package(PNGwriter 0.7.0 CONFIG)`     |
| `hdf5`     | 1.14.6          | `HDF5_ROOT`    | (transitively by openPMD, parallel)          |
| `adios2`   | 2.11.0          | `ADIOS2_ROOT`  | (transitively by openPMD)                    |
| `openpmd`  | 0.17.1          | `OPENPMD_ROOT` | `find_package(openPMD 0.15 CONFIG COMPONENTS MPI)` |
| `fftw3`    | 3.3.10          | `FFTW3_ROOT`   | `pkg_check_modules(FFTW3 fftw3)` (pkg-config)|

This generalises the old per-cluster `dependencies_autoinstall.sh` scripts
(rosi-hzdr, delta-ncsa, perlmutter-nersc), which are now thin wrappers
around `picongpu-deps.sh`.

## Quick start

```bash
# on a cluster, after loading the toolchain and your PIConGPU profile:
bash picongpu-deps.sh                      # install everything that is missing
bash picongpu-deps.sh --only=fftw3,pngwriter
bash picongpu-deps.sh --list               # show the dependency table
bash picongpu-deps.sh --help
```

Everything is installed into **user-owned prefixes** (no root required) and
is **idempotent**: existing installations are detected via
`.picongpu-deps.stamp` marker files and skipped.

## Target modes

- **Cluster mode** - if your profile exports the `<dep>_ROOT` variables
  (e.g. `HDF5_ROOT=$ROSI_LIB/HDF5/...`), each dependency is installed into
  that prefix. This reproduces the old per-cluster behaviour, including
  shared installs on cluster filesystems.
- **Managed mode** - without a profile (e.g. a laptop), dependencies are
  installed into `<DEPS_INSTALL_ROOT>/<toolchain-key>/<name>-<version>` and
  an environment file is generated:

  ```bash
  DEPS_INSTALL_ROOT=$HOME/mydeps bash picongpu-deps.sh --only=fftw3,pngwriter
  source "$DEPS_INSTALL_ROOT/current.env"   # sets *_ROOT, CMAKE_PREFIX_PATH, ...
  pic-build ...
  ```

  `current.env` always points at the most recent toolchain key.

## Cache layout

```
$DEPS_INSTALL_ROOT/
  sources/                  # shared source cache, fetched ONCE (login node)
    boost_1_87_0.tar.gz
    fftw-3.3.10.tar.gz
    git/{pngwriter,hdf5,adios2,openpmd,c-blosc2}/
  <toolchain-key>/          # e.g. eeb9368ec6cb-x86_64
    fingerprint.txt         # compiler/MPI/CMake/arch/versions used
    src/                    # working source copies
    build/                  # build trees
    logs/<dep>.log          # build logs
    <name>-<version>/       # installed prefixes (+ .picongpu-deps.stamp)
    picongpu-deps.env
  current.env               # copy of the newest key's env file
```

The **toolchain key** is a hash of: C/C++ compiler version, MPI wrapper
version, CMake version, architecture, and all dependency versions. A prefix
built for a different key is detected and skipped with a warning
(set `DEPS_FORCE=1` to rebuild). This is what makes repeated runs cheap
(measured: full subset cold build ~3 min on 16 cores, warm run ~0.2 s) and
what prevents mixing binary-incompatible toolchains.

**Login vs. compute:** run the script once with network access to fill
`sources/`; afterwards compute nodes can use `--offline` (`DEPS_OFFLINE=1`)
and only need the toolchain, no network.

## Configuration (environment variables)

| variable | meaning |
|----------|---------|
| `DEPS_PROVIDER` | `source` (default) \| `conda` \| `modules` \| `container` |
| `DEPS_ONLY` | comma-separated subset of keys |
| `DEPS_JOBS` | parallel build jobs (default: `nproc`) |
| `DEPS_INSTALL_ROOT` | managed-mode install root |
| `DEPS_SOURCE_CACHE` | shared source cache directory |
| `DEPS_FORCE` | `1`: rebuild even if the target exists |
| `DEPS_OFFLINE` | `1`: never touch the network |
| `DEPS_QUIET` | `1`: send build output to log files only |
| `DEPS_CC` / `DEPS_CXX` | compilers (default: `cc` / `CC`) |
| `DEPS_MPI_C` / `DEPS_MPI_CXX` | MPI wrappers (default: `$MPI_CC`/`$MPI_CXX`, else `mpicc`/`mpicxx` on PATH) |
| `DEPS_MPI_DIR` | prefix of the MPI installation (header/library hints) |
| `DEPS_ADIOS2_PATCH_CLIENT_SERVER` | `1`: apply the perlmutter MPICH patch to ADIOS2 |
| `DEPS_<NAME>_VERSION` | version override (`NAME` = `BOOST`, `C_BLOSC2`, `LIBPNG`, `PNGWRITER`, `HDF5`, `ADIOS2`, `OPENPMD`, `FFTW3`); profile variables (`<NAME>_VERSION`) are the fallback |
| `DEPS_BOOST_LIBRARIES` | Boost libraries to build |
| `DEPS_OPENPMD_USE_HDF5` / `DEPS_OPENPMD_USE_ADIOS2` | force `ON`/`OFF` (default: auto-detect what exists) |
| `DEPS_CMAKE_PREFIX_HINT` | extra `CMAKE_PREFIX_PATH` for the dependency builds |
| `DEPS_CMAKE_EXTRA_BLOSC2` / `_PNGWRITER` / `_HDF5` / `_ADIOS2` / `_OPENPMD` | escape hatch: extra `-D...` flags per dependency (per-cluster quirks) |
| `DEPS_FFTW_CONFIGURE_EXTRA` | extra `./configure` flags for FFTW |

## Notes and known limitations

- **PNGwriter** declares `cmake_minimum_required(VERSION 2.8.12)`; the
  installer passes `CMAKE_POLICY_VERSION_MINIMUM=3.5`, which is required
  for CMake >= 3.27/4.x and a no-op for older CMake.
- **libpng/FFTW3** are autotools builds and need the usual system
  companions (zlib for libpng). These are expected to come from the
  loaded toolchain (modules), as on the clusters.
- The `source` provider **does not manage the toolchain** (compiler,
  CUDA/HIP, MPI itself) - that stays the job of the preset/profile.
- The `conda` provider (draft) activates a conda environment and writes
  the env file from its prefix; **PNGwriter is not on conda-forge**, so it
  still needs a `source` build (`--only=pngwriter`).
- The `container` provider is a stub (connects with the EFP container path).
- A full ADIOS2+Boost stack adds roughly 10-30 min of build time on 16
  cores; that is why the cache (and the `modules`/`conda` providers) exist.
