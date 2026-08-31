#!/usr/bin/env bash
# Copyright 2023-2026 Axel Huebl, Marco Garten, Klaus Steiniger, Pawel Ordyna,
#                     Richard Pausch
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
# Dependency installation for delta / NCSA.
#
# Thin wrapper around the shared, parameterised installer
# etc/picongpu/dependencies/picongpu-deps.sh (DRAFT).
#
# NOTE: DRAFT - reproduces the old per-cluster install *in intent*, but the
# shared installer has only been validated locally so far; run at least
# `bash <this script> --list` and a dry cache-hit run before relying on it.
#
# The wrapper sources $PIC_PROFILE (the shared installer does so again,
# which is harmless) so that the cluster settings below can use the
# profile's variables ($DELTA_LIB, $MPI_CXX, ...).

if [ -z "${PIC_PROFILE:-}" ] || [ ! -f "${PIC_PROFILE:-}" ]; then
    printf 'Set PIC_PROFILE to your PIConGPU profile (e.g. etc/picongpu/delta-ncsa/gpuA100x4_picongpu.profile.example)!\n'
    exit 1
fi
# shellcheck disable=SC1090
source "$PIC_PROFILE"

# cluster-specific settings for the shared installer
export DEPS_JOBS=${DEPS_JOBS:-16}
# shared source cache on the cluster filesystem (fetch once per cluster)
export DEPS_SOURCE_CACHE=${DEPS_SOURCE_CACHE:-"$DELTA_LIB/deps-sources"}

# The old delta script pointed ADIOS2/openPMD at this MPI library:
#   -DMPI_mpi_gnu_123_LIBRARY=<mpi prefix>/lib/libmpi_gnu_123.so
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
