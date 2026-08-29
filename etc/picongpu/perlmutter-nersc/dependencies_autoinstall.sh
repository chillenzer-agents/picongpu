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
# The profile (sourced by the shared installer via $PIC_PROFILE)
# exports the *_ROOT prefixes and versions; the shared installer
# fills them in. Cluster-specific settings go below.

if [ ! -f "${PIC_PROFILE:-}" ]; then
    printf 'Source a PIConGPU profile first (e.g. gpu.profile.example)!\n'
    exit 1
fi

# cluster-specific settings for the shared installer
export DEPS_JOBS=${DEPS_JOBS:-16}
# shared source cache on the scratch filesystem (fetch once per cluster)
if [ -n "${CFS:-}${proj:-}" ]; then
    export DEPS_SOURCE_CACHE=${DEPS_SOURCE_CACHE:-"$CFS/$proj/$USER/deps-sources"}
fi
# perlmutter uses MPICH; the old script patched ADIOS2's client/server check
export DEPS_ADIOS2_PATCH_CLIENT_SERVER=1
# If ADIOS2/openPMD need extra CMake flags for this cluster's MPI, use the
# escape hatches, e.g.:
# export DEPS_CMAKE_EXTRA_ADIOS2="-D..."
# export DEPS_CMAKE_EXTRA_OPENPMD="-D..."

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
