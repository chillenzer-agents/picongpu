#!/usr/bin/env bash
# Copyright 2026 PIConGPU contributors
#
# This file is part of PIConGPU.
#
# PIConGPU is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# PIConGPU is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with PIConGPU.
# If not, see <http://www.gnu.org/licenses/>.
#
# picongpu-deps.sh (DRAFT) - general, portable installation of the
# compiled C++ dependencies of PIConGPU (boost, c-blosc2, libpng,
# pngwriter, hdf5, adios2, openpmd, fftw3).
#
# Usage (after loading the toolchain, and the PIConGPU profile if you have
# one that exports the dependency prefixes):
#
#     bash picongpu-deps.sh                  # install everything missing
#     bash picongpu-deps.sh --only=fftw3,pngwriter
#     bash picongpu-deps.sh --help
#
# The script is parameterised entirely through environment variables
# (see --help and README.md). It can be executed or sourced; all results
# are on disk (install prefixes, cache, generated env files), so sourcing
# does not leak build state into your shell.

set -eu -o pipefail

DEPS_SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=picongpu-deps-lib.sh
source "$DEPS_SCRIPT_DIR/picongpu-deps-lib.sh"

deps_usage() {
    cat <<'EOF'
picongpu-deps.sh (DRAFT) - install the compiled dependencies of PIConGPU

Usage:
  bash picongpu-deps.sh [options]

Options:
  --help                show this help
  --list                show the dependency table and exit
  --only=a,b,c          only handle a subset (boost,c-blosc2,libpng,
                        pngwriter,hdf5,adios2,openpmd,fftw3)
  --jobs=N              parallel build jobs (default: number of cores)
  --prefix=PATH         managed install root (default: ~/.picongpu/deps,
                        or $PIC_LIBS/picongpu-deps if PIC_LIBS is set)
  --cache=PATH          shared source cache (default: <prefix>/sources)
  --force               rebuild even if the target prefix exists
  --offline             never touch the network (cache must be warm)
  --quiet               send build output to log files only
  --provider=NAME       source (default) | conda | modules | container

Environment variables (all optional):
  DEPS_PROVIDER        provider, default "source"
  DEPS_ONLY            subset, e.g. "fftw3,pngwriter"
  DEPS_JOBS            parallel jobs (default: nproc)
  DEPS_INSTALL_ROOT    managed install root
  DEPS_SOURCE_CACHE    shared source cache directory
  DEPS_FORCE=1         rebuild existing prefixes
  DEPS_OFFLINE=1       no network access
  DEPS_QUIET=1         log builds instead of streaming them
  DEPS_CXXSTD          C++ standard passed to boost (default: c++20)
  DEPS_CC / DEPS_CXX   compilers (default: cc / CC or g++/clang++)
  DEPS_MPI_C / DEPS_MPI_CXX
                       MPI wrappers (default: $MPI_CC/$MPI_CXX, else
                       mpicc/mpicxx on PATH)
  DEPS_MPI_DIR         prefix of the MPI installation (header/library
                       hints for ADIOS2/openPMD; default: derived from
                       the MPI wrapper)
  DEPS_ADIOS2_PATCH_CLIENT_SERVER=1
                       apply the perlmutter-style MPICH patch to ADIOS2
  DEPS_FFTW_CONFIGURE_EXTRA
                       extra ./configure flags for FFTW
  DEPS_<NAME>_VERSION  version override per dependency
                       (NAME = BOOST, C_BLOSC2, LIBPNG, PNGWRITER, HDF5,
                       ADIOS2, OPENPMD, FFTW3); the profile variables
                       (<NAME>_VERSION) are used as fallback
  DEPS_BOOST_LIBRARIES boost libraries to build (default: the set used
                       by the old per-cluster scripts)
  DEPS_OPENPMD_USE_HDF5 / DEPS_OPENPMD_USE_ADIOS2
                       force on/off (default: auto-detect what exists)
  DEPS_CMAKE_PREFIX_HINT
                       colon-separated extra CMAKE_PREFIX_PATH for the
                       dependency builds
  DEPS_CMAKE_EXTRA_BLOSC2 / _PNGWRITER / _HDF5 / _ADIOS2 / _OPENPMD
                       escape hatch: extra -D flags for a dependency
                       (per-cluster quirks, e.g. -DMPI_mpi_gnu_123_LIBRARY=...)

Target modes:
  cluster mode: if the environment already exports <dep>_ROOT variables
  (BOOST_ROOT, BLOSC_ROOT, LIBPNG_ROOT, PNGwriter_ROOT, HDF5_ROOT,
  ADIOS2_ROOT, OPENPMD_ROOT, FFTW3_ROOT), e.g. from a PIConGPU profile,
  dependencies are installed into those prefixes (old behaviour).
  managed mode: otherwise, they are installed into
  <DEPS_INSTALL_ROOT>/<toolchain-key>/<name>-<version> and a
  picongpu-deps.env / current.env is generated; source current.env
  before configuring PIConGPU with CMake.
EOF
}

deps_list() {
    printf '%-10s %-12s %-20s %s\n' "key" "version" "root variable" "source"
    local key
    for key in "${DEPS_KEYS[@]}"; do
        printf '%-10s %-12s %-20s %s\n' \
            "$key" \
            "$(deps_resolve_version "$key")" \
            "${DEPS_ROOT_VAR[$key]}" \
            "see README.md"
    done
}

deps_main() {
    local only=""
    local prefix=""
    local cache=""
    local jobs=""
    local arg
    for arg in "$@"; do
        case "$arg" in
        -h | --help)
            deps_usage
            return 0
            ;;
        --list)
            deps_list
            return 0
            ;;
        --only=*)
            only=${arg#*=}
            ;;
        --prefix=*)
            prefix=${arg#*=}
            ;;
        --cache=*)
            cache=${arg#*=}
            ;;
        --jobs=*)
            jobs=${arg#*=}
            ;;
        --force)
            export DEPS_FORCE=1
            ;;
        --offline)
            export DEPS_OFFLINE=1
            ;;
        --quiet)
            export DEPS_QUIET=1
            ;;
        --provider=*)
            export DEPS_PROVIDER=${arg#*=}
            ;;
        *)
            deps_usage
            return 1
            ;;
        esac
    done

    # if run (not sourced) and a profile is available, load it: this is how
    # the per-cluster wrappers work (profile already sourced, or PIC_PROFILE
    # points at it). Sourcing a profile twice is harmless (re-exports).
    if [ -n "${PIC_PROFILE:-}" ] && [ -f "$PIC_PROFILE" ]; then
        # shellcheck disable=SC1090
        source "$PIC_PROFILE"
    fi

    # --- resolve configuration with defaults --------------------------------
    [ -n "$only" ] && export DEPS_ONLY="$only"
    [ -n "${DEPS_ONLY:-}" ] || DEPS_ONLY=""
    DEPS_PROVIDER=${DEPS_PROVIDER:-source}
    DEPS_JOBS=${jobs:-${DEPS_JOBS:-$(nproc 2>/dev/null || echo 4)}}
    DEPS_CXXSTD=${DEPS_CXXSTD:-c++20}
    DEPS_CC=${DEPS_CC:-$(command -v cc || command -v gcc || true)}
    DEPS_CXX=${DEPS_CXX:-$(command -v CC || command -v c++ || command -v g++ || true)}
    DEPS_BOOST_LIBRARIES=${DEPS_BOOST_LIBRARIES:-atomic,chrono,context,date_time,fiber,filesystem,math,program_options,serialization,system,thread}
    if [ -n "$prefix" ]; then
        DEPS_INSTALL_ROOT=$prefix
    else
        DEPS_INSTALL_ROOT=${DEPS_INSTALL_ROOT:-}
        if [ -z "$DEPS_INSTALL_ROOT" ]; then
            if [ -n "${PIC_LIBS:-}" ]; then
                DEPS_INSTALL_ROOT="$PIC_LIBS/picongpu-deps"
            else
                DEPS_INSTALL_ROOT="$HOME/.picongpu/deps"
            fi
        fi
    fi
    DEPS_SOURCE_CACHE=${cache:-${DEPS_SOURCE_CACHE:-$DEPS_INSTALL_ROOT/sources}}

    if [ "$DEPS_PROVIDER" = "source" ]; then
        # --- check the toolchain -------------------------------------------
        local missing=0
        local tool
        for tool in cmake make; do
            if ! command -v "$tool" >/dev/null 2>&1; then
                deps_warn "required tool '$tool' not found on PATH"
                missing=1
            fi
        done
        if [ -z "$DEPS_CC" ] || [ -z "$DEPS_CXX" ]; then
            deps_warn "no C/C++ compiler found (set DEPS_CC/DEPS_CXX); the 'source' provider needs a toolchain"
            missing=1
        fi
        if [ "$missing" -eq 1 ]; then
            deps_die "toolchain incomplete; the 'source' provider cannot work here (try --provider=modules to only verify existing installs)"
        fi

        deps_detect_mpi
        if [ -z "${DEPS_MPI_CXX:-}" ]; then
            deps_warn "no MPI wrapper found (mpicxx/mpic++); parallel HDF5/ADIOS2/openPMD cannot be built - fine for a minimal subset like FFTW3+PNGwriter"
        fi
        deps_compute_key
        DEPS_KEY_DIR="$DEPS_INSTALL_ROOT/$DEPS_KEY"
        mkdir -p "$DEPS_KEY_DIR/src" "$DEPS_KEY_DIR/build" "$DEPS_KEY_DIR/logs" "$DEPS_SOURCE_CACHE"
        printf '%s\n' "$DEPS_FINGERPRINT" >"$DEPS_KEY_DIR/fingerprint.txt"
        deps_log "toolchain key: $DEPS_KEY"
        deps_log "install root: $DEPS_INSTALL_ROOT"
        deps_log "source cache: $DEPS_SOURCE_CACHE"
    fi

    case "$DEPS_PROVIDER" in
    source)
        deps_provider_source
        ;;
    conda)
        deps_provider_conda
        ;;
    modules)
        deps_provider_modules
        ;;
    container)
        deps_provider_container
        ;;
    *)
        deps_die "unknown provider '$DEPS_PROVIDER' (valid: source, conda, modules, container)"
        ;;
    esac
}

if deps_is_sourced; then
    # keep the user's shell clean: flags, traps and variables stay in a
    # subshell; everything of value is written to disk
    (set -eu -o pipefail; deps_main "$@")
else
    trap 'deps_write_summary' EXIT
    deps_main "$@"
fi
