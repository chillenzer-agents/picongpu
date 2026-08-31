#!/usr/bin/env bash
# Copyright 2023-2026 Axel Huebl, Marco Garten, Klaus Steiniger, Pawel Ordyna
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
# Dependency installation for perlmutter / NERSC.
#
# Thin wrapper around the shared, parameterised installer
# etc/picongpu/dependencies/picongpu-deps.sh (DRAFT).
#
# NOTE: DRAFT - reproduces the old per-cluster install *in intent*, but the
# shared installer has only been validated locally so far; run at least
# `bash <this script> --list` and a dry cache-hit run before relying on it.
#
# Scope (matches the old perlmutter script): the cluster modules provide
# libpng, HDF5 and FFTW, so only boost, c-blosc2, pngwriter, adios2 and
# openpmd are built; openPMD is built with the module's (parallel) HDF5.
#
# The wrapper sources $PIC_PROFILE (the shared installer does so again,
# which is harmless) so that the cluster settings below can use the
# profile's variables ($CFS/$proj, $MPI_CXX, ...).

if [ -z "${PIC_PROFILE:-}" ] || [ ! -f "${PIC_PROFILE:-}" ]; then
    printf 'Set PIC_PROFILE to your PIConGPU profile (e.g. etc/picongpu/perlmutter-nersc/gpu.profile.example)!\n'
    exit 1
fi
# shellcheck disable=SC1090
source "$PIC_PROFILE"

# cluster-specific settings for the shared installer
export DEPS_JOBS=${DEPS_JOBS:-16}
# shared source cache on the scratch filesystem (fetch once per cluster)
if [ -n "${CFS:-}" ] && [ -n "${proj:-}" ]; then
    export DEPS_SOURCE_CACHE=${DEPS_SOURCE_CACHE:-"$CFS/$proj/$USER/deps-sources"}
fi
# perlmutter uses MPICH; the old script patched ADIOS2's client/server check
export DEPS_ADIOS2_PATCH_CLIENT_SERVER=1
# modules provide libpng/HDF5/FFTW; build the rest (old script's scope)
export DEPS_ONLY=${DEPS_ONLY:-boost,c-blosc2,pngwriter,adios2,openpmd}
# the module's parallel HDF5 is not at a DEPS/HDF5_ROOT location, so tell
# openPMD to enable the HDF5 backend explicitly (the old script hardcoded ON)
export DEPS_OPENPMD_USE_HDF5=${DEPS_OPENPMD_USE_HDF5:-ON}

# The old perlmutter script pointed ADIOS2/openPMD at this MPI library:
#   -DMPI_mpi_gnu_123_LIBRARY=${MPICH_DIR}/lib/libmpi_gnu_123.so
# Default the equivalent DEPS_CMAKE_EXTRA_* flags when the library exists
# (the profile's MPI module must be loaded, as by sourcing the profile).
if [ -z "${DEPS_CMAKE_EXTRA_ADIOS2:-}" ]; then
    _deps_mpi_cxx="${MPI_CXX:-}"
    if [ ! -x "$_deps_mpi_cxx" ]; then
        _deps_mpi_cxx=$(command -v mpicxx 2>/dev/null || true)
    fi
    if [ -n "$_deps_mpi_cxx" ]; then
        _deps_mpi_prefix=$(cd "$(dirname "$_deps_mpi_cxx")/.." 2>/dev/null && pwd)
    fi
    if [ -n "${_deps_mpi_prefix:-}" ] && [ -f "$_deps_mpi_prefix/lib/libmpi_gnu_123.so" ]; then
        export DEPS_CMAKE_EXTRA_ADIOS2="-DMPI_mpi_gnu_123_LIBRARY=$_deps_mpi_prefix/lib/libmpi_gnu_123.so"
        export DEPS_CMAKE_EXTRA_OPENPMD="-DMPI_mpi_gnu_123_LIBRARY=$_deps_mpi_prefix/lib/libmpi_gnu_123.so"
    else
        printf '[deps] note: <mpi prefix>/lib/libmpi_gnu_123.so not found; the legacy -DMPI_mpi_gnu_123_LIBRARY hint is not set. Override via DEPS_CMAKE_EXTRA_ADIOS2 / DEPS_CMAKE_EXTRA_OPENPMD if needed.\n' >&2
    fi
fi

DEPS_INSTALLER=""
for cand in \
    "${PICSRC:-}/etc/picongpu/dependencies/picongpu-deps.sh" \
    "$(cd "$(dirname "${BASH_SOURCE[0]}")/../dependencies" && pwd)/picongpu-deps.sh"; do
    if [ -f "$cand" ]; then
        DEPS_INSTALLER=$cand
        break
    fi
done
if [ -z "$DEPS_INSTALLER" ]; then
    printf 'Could not find the shared installer etc/picongpu/dependencies/picongpu-deps.sh.\n'
    printf 'Set PICSRC to your PIConGPU checkout, or run it from a checkout of PIConGPU.\n'
    exit 1
fi

exec bash "$DEPS_INSTALLER" "$@"
