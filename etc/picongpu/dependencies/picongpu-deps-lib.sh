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
# Shared library for picongpu-deps.sh (DRAFT).
#
# Parameterised, idempotent, cache-backed source installation of the
# compiled C++ dependencies of PIConGPU:
#
#     boost, c-blosc2, libpng, pngwriter, hdf5, adios2, openpmd, fftw3
#
# Design goals:
#   - no root required: everything is installed into user-owned prefixes
#   - toolchain heterogeneity: build against the *loaded* compiler/MPI
#   - repeated runs are cheap: shared, toolchain-keyed cache
#   - login vs compute: sources are fetched once into a shared cache
#
# Two target modes:
#   - cluster mode: a PIConGPU profile exported <dep>_ROOT variables
#     (e.g. HDF5_ROOT); each dependency is installed into that prefix.
#     This reproduces the old per-cluster dependencies_autoinstall.sh.
#   - managed mode: no *_ROOT in the environment; dependencies are
#     installed into a toolchain-keyed directory under DEPS_INSTALL_ROOT
#     and an environment file (picongpu-deps.env, plus a stable
#     "current.env") is generated for the build/run scripts to source.
#
# This library is meant to be sourced by picongpu-deps.sh, not executed.

# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

deps_log() {
    printf '[picongpu-deps] %s\n' "$*"
}

deps_warn() {
    printf '[picongpu-deps] WARNING: %s\n' "$*" >&2
}

# exit() would kill the shell of users who source the main script,
# so when sourced we return instead.
deps_die() {
    printf '[picongpu-deps] ERROR: %s\n' "$1" >&2
    if [ -n "${BASH_SOURCE:-}" ] && [ "${BASH_SOURCE}" != "$0" ]; then
        return 1
    fi
    exit 1
}

deps_is_sourced() {
    [ -n "${BASH_SOURCE:-}" ] && [ "${BASH_SOURCE}" != "$0" ]
}

# ---------------------------------------------------------------------------
# dependency table (order = build order)
# ---------------------------------------------------------------------------

DEPS_KEYS=(boost c-blosc2 libpng pngwriter hdf5 adios2 openpmd fftw3)

# environment variable the profile/preset uses to expose each prefix
declare -A DEPS_ROOT_VAR=(
    [boost]="BOOST_ROOT"
    [c-blosc2]="BLOSC_ROOT"
    [libpng]="LIBPNG_ROOT"
    [pngwriter]="PNGwriter_ROOT"
    [hdf5]="HDF5_ROOT"
    [adios2]="ADIOS2_ROOT"
    [openpmd]="OPENPMD_ROOT"
    [fftw3]="FFTW3_ROOT"
)

# version variable exported by cluster profiles (fallback lookup)
declare -A DEPS_VERSION_VAR=(
    [boost]="BOOST_VERSION"
    [c-blosc2]="BLOSC_VERSION"
    [libpng]="LIBPNG_VERSION"
    [pngwriter]="PNGWRITER_VERSION"
    [hdf5]="HDF5_VERSION"
    [adios2]="ADIOS2_VERSION"
    [openpmd]="OPENPMD_VERSION"
    [fftw3]="FFTW_VERSION"
)

# default versions when neither DEPS_*_VERSION nor the profile sets one
declare -A DEPS_DEFAULT_VERSION=(
    [boost]="1.87.0"
    [c-blosc2]="2.22.0"
    [libpng]="1.6.34"
    [pngwriter]="0.7.0"
    [hdf5]="1.14.6"
    [adios2]="2.11.0"
    [openpmd]="0.17.1"
    [fftw3]="3.3.10"
)

# directory name inside a managed (un-keyed-by-profile) prefix
declare -A DEPS_DIRNAME=(
    [boost]="boost"
    [c-blosc2]="c-blosc2"
    [libpng]="libpng"
    [pngwriter]="pngwriter"
    [hdf5]="hdf5"
    [adios2]="adios2"
    [openpmd]="openpmd-api"
    [fftw3]="fftw3"
)

# key -> install function. Function names are always underscored; the keys
# keep their human form (e.g. "c-blosc2"), so the mapping must be explicit:
# "deps_install_$key" can never be formed for a key containing a dash.
declare -A DEPS_FN=(
    [boost]="deps_install_boost"
    [c-blosc2]="deps_install_c_blosc2"
    [libpng]="deps_install_libpng"
    [pngwriter]="deps_install_pngwriter"
    [hdf5]="deps_install_hdf5"
    [adios2]="deps_install_adios2"
    [openpmd]="deps_install_openpmd"
    [fftw3]="deps_install_fftw3"
)

# pinned sha256 of the default-version tarballs (corruption/MITM defence for
# the shared source cache). Version overrides that are not listed here still
# get a completeness check (deps_tarball_intact) before caching.
declare -A DEPS_SHA256=(
    [boost_1_87_0.tar.gz]="f55c340aa49763b1925ccf02b2e83f35fdcf634c9d5164a2acb87540173c741d"
    [libpng-1.6.34.tar.gz]="574623a4901a9969080ab4a2df9437026c8a87150dfd5c235e28c94b212964a7"
    [fftw-3.3.10.tar.gz]="56c932549852cddcfafdab3820b0200c7742675be92179e59e6215b340e26467"
)

deps_dep_requested() {
    local key=$1
    local wanted
    if [ -z "${DEPS_ONLY:-}" ]; then
        return 0
    fi
    for wanted in $(echo "$DEPS_ONLY" | tr ',' ' '); do
        if [ "$wanted" = "$key" ]; then
            return 0
        fi
    done
    return 1
}

deps_resolve_version() {
    local key=$1
    local var
    printf -v var 'DEPS_%s_VERSION' "$(echo "$key" | tr 'a-z-' 'A-Z_')"
    # profile fallback (e.g. HDF5_VERSION exported by the profile)
    local profile_var="${DEPS_VERSION_VAR[$key]}"
    if [ -n "${!var:-}" ]; then
        printf '%s' "${!var}"
    elif [ -n "${!profile_var:-}" ]; then
        printf '%s' "${!profile_var}"
    else
        printf '%s' "${DEPS_DEFAULT_VERSION[$key]}"
    fi
}

# resolve the install target for a dependency:
# cluster mode -> the *_ROOT exported by the profile
# managed mode -> $DEPS_INSTALL_ROOT/$DEPS_KEY/<dirname>-<version>
deps_target() {
    local key=$1
    local version=$2
    local root_var="${DEPS_ROOT_VAR[$key]}"
    if [ -n "${!root_var:-}" ]; then
        printf '%s' "${!root_var}"
    else
        printf '%s' "$DEPS_INSTALL_ROOT/$DEPS_KEY/${DEPS_DIRNAME[$key]}-$version"
    fi
}

# true if the (resolved) target of a dependency exists on disk
deps_dep_installed() {
    local key=$1
    local version=$2
    [ -d "$(deps_target "$key" "$version")" ]
}

# ---------------------------------------------------------------------------
# toolchain fingerprint and cache key
# ---------------------------------------------------------------------------

deps_hash() {
    if command -v sha256sum >/dev/null 2>&1; then
        printf '%s' "$1" | sha256sum | cut -c1-12
    else
        # macOS fallback
        printf '%s' "$1" | shasum -a 256 | cut -c1-12
    fi
}

deps_compute_key() {
    local ccv cxxv mpiv cmakev arch
    ccv=$("$DEPS_CC" --version 2>/dev/null | head -n1 || echo "cc?")
    cxxv=$("$DEPS_CXX" --version 2>/dev/null | head -n1 || echo "c++?")
    mpiv=$("${DEPS_MPI_CXX:-true}" --version 2>/dev/null | head -n1 || echo "mpi?")
    cmakev=$(cmake --version 2>/dev/null | head -n1 || echo "cmake?")
    arch=$(uname -m)

    local versions_line=""
    local v
    for v in "${DEPS_KEYS[@]}"; do
        versions_line+="$v=$(deps_resolve_version "$v") "
    done

    DEPS_FINGERPRINT=$(
        printf '%s\n' \
            "cc: $ccv" \
            "cxx: $cxxv" \
            "mpi: $mpiv" \
            "cmake: $cmakev" \
            "arch: $arch" \
            "versions: $versions_line"
    )
    DEPS_KEY="$(deps_hash "$DEPS_FINGERPRINT")-$(uname -m)"
}

# ---------------------------------------------------------------------------
# fetching sources (once) into the shared source cache
# ---------------------------------------------------------------------------

deps_require_online() {
    if [ "${DEPS_OFFLINE:-0}" -eq 1 ]; then
        deps_warn "DEPS_OFFLINE=1 but the source is not in $DEPS_SOURCE_CACHE yet. Run once with network access (login node) first, or copy the source cache."
        return 1
    fi
}

deps_sha256() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | cut -d' ' -f1
    else
        shasum -a 256 "$1" | cut -d' ' -f1
    fi
}

# a .tar.gz is "intact" if it lists its contents; this is the cheap
# completeness check for downloads whose version has no pinned checksum
deps_tarball_intact() {
    tar -tzf "$1" >/dev/null 2>&1
}

deps_fetch_tarball() {
    local url=$1
    local name=$2
    local dest="$DEPS_SOURCE_CACHE/$name"
    if [ -f "$dest" ] && deps_tarball_intact "$dest"; then
        deps_log "source cache hit: $name"
        return 0
    fi
    if [ -f "$dest" ]; then
        deps_warn "$name: cached copy is not a readable tarball; removing and refetching"
        rm -f "$dest"
    fi
    deps_require_online || return 1
    deps_log "fetching $url -> $dest"
    local rc=0
    if command -v curl >/dev/null 2>&1; then
        curl -fL --retry 3 --connect-timeout 30 -o "$dest.part" "$url" || rc=$?
    else
        wget -O "$dest.part" "$url" || rc=$?
    fi
    if [ "$rc" -ne 0 ]; then
        rm -f "$dest.part"
        deps_warn "$name: download failed (rc=$rc); no partial file kept in $DEPS_SOURCE_CACHE"
        return 1
    fi
    local want="${DEPS_SHA256[$name]:-}"
    if [ -n "$want" ]; then
        local got
        got=$(deps_sha256 "$dest.part")
        if [ "$got" != "$want" ]; then
            rm -f "$dest.part"
            deps_warn "$name: checksum mismatch (want $want, got $got); removing the file"
            return 1
        fi
    fi
    if ! deps_tarball_intact "$dest.part"; then
        rm -f "$dest.part"
        deps_warn "$name: downloaded file is not a readable tarball; removing it"
        return 1
    fi
    mv "$dest.part" "$dest"
}

# git source cache, keyed by name AND tag: a version override must not
# silently reuse a checkout of a different tag
deps_git_cache_dir() {
    # $1 name, $2 tag
    printf '%s' "$DEPS_SOURCE_CACHE/git/$1-$2"
}

deps_fetch_git() {
    local url=$1
    local tag=$2
    local name=$3
    local dir
    dir=$(deps_git_cache_dir "$name" "$tag")
    if [ -d "$dir/.git" ]; then
        deps_log "source cache hit: git:$name-$tag"
        return 0
    fi
    deps_require_online || return 1
    deps_log "cloning $url ($tag) -> $dir"
    local rc=0
    git clone --depth 1 --branch "$tag" "$url" "$dir" || rc=$?
    if [ "$rc" -ne 0 ]; then
        rm -rf "$dir"
        deps_warn "$name: git clone of $tag failed (rc=$rc); removing the partial clone"
        return 1
    fi
}

# create a working copy of a source in the toolchain-keyed build area;
# prints the path of the working copy (callers capture it)
deps_prepare_source_copy() {
    local name=$1
    local src=$2
    local dest="$DEPS_KEY_DIR/src/$name"
    if [ -e "$dest" ]; then
        rm -rf "$dest"
    fi
    if [ -d "$src/.git" ]; then
        git clone --quiet --local "$src" "$dest"
    else
        cp -r "$src" "$dest"
    fi
    printf '%s' "$dest"
}

# ---------------------------------------------------------------------------
# idempotency guard, stamp, timing
# ---------------------------------------------------------------------------

DEPS_SUMMARY=()

deps_guard() {
    local key=$1
    local target=$2
    if [ "${DEPS_FORCE:-0}" -eq 0 ] && [ -d "$target" ] && [ -z "$(ls -A "$target" 2>/dev/null)" ]; then
        # empty directory: a previous (failed) run of this tool; safe to reuse
        deps_log "$key: reusing empty target $target from a previous failed run"
        return 0
    fi
    if [ "${DEPS_FORCE:-0}" -eq 0 ] && [ -d "$target" ]; then
        if [ -f "$target/.picongpu-deps.stamp" ]; then
            local stamp_key
            stamp_key=$(grep '^key=' "$target/.picongpu-deps.stamp" | cut -d= -f2 || true)
            if [ "$stamp_key" = "$DEPS_KEY" ]; then
                deps_log "$key: already installed at $target (cache hit, skipping)"
                return 1
            fi
            deps_warn "$key: $target exists but was built for a different toolchain (key $stamp_key, current $DEPS_KEY). Skipping; set DEPS_FORCE=1 to rebuild."
            return 1
        elif [ -f "$target/.picongpu-deps.inprogress" ]; then
            deps_log "$key: previous build in $target was interrupted (no stamp); rebuilding in place"
            rm -f "$target/.picongpu-deps.inprogress"
            return 0
        fi
        deps_log "$key: pre-existing installation at $target (no stamp; e.g. from an old per-cluster script), skipping; set DEPS_FORCE=1 to rebuild."
        return 1
    fi
    if [ -e "$target" ]; then
        deps_log "$key: DEPS_FORCE=1, removing stale $target"
        rm -rf "$target"
    fi
    mkdir -p "$target"
    # marks the target as being built by this tool; removed by deps_stamp on
    # success. A failed run therefore never leaves a target that looks
    # "installed" and is always retried on the next run.
    touch "$target/.picongpu-deps.inprogress"
    return 0
}

deps_stamp() {
    local key=$1
    local target=$2
    {
        printf 'key=%s\n' "$DEPS_KEY"
        printf 'dep=%s\n' "$key"
        printf 'date=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
        printf 'version=%s\n' "$(deps_resolve_version "$key")"
        printf 'cxx=%s\n' "$("$DEPS_CXX" --version 2>/dev/null | head -n1 || echo unknown)"
    } >"$target/.picongpu-deps.stamp"
    rm -f "$target/.picongpu-deps.inprogress"
}

# run a build command, logging into the cache and measuring the time.
# Returns the command's rc (non-zero on failure) so the caller can record
# the failure and abort the remaining dependencies; a failed build must
# never be stamped as installed.
deps_build() {
    local key=$1
    shift
    local log="$DEPS_KEY_DIR/logs/$key.log"
    deps_log "$key: building (log: $log)"
    local rc=0
    if [ "${DEPS_QUIET:-0}" -eq 1 ]; then
        "$@" >>"$log" 2>&1
        rc=$?
    else
        # PIPESTATUS must be read immediately after the pipeline; a trailing
        # "|| rc=..." would only fire if tee itself failed
        "$@" 2>&1 | tee "$log"
        rc=${PIPESTATUS[0]}
    fi
    if [ $rc -ne 0 ]; then
        deps_warn "$key: build step failed (rc=$rc), see $log"
        return "$rc"
    fi
}

# record the per-dependency result for the final summary
deps_record() {
    # $1 key, $2 rc, $3 seconds
    DEPS_SUMMARY+=("$1|$2|$3")
}

# ---------------------------------------------------------------------------
# MPI detection
# ---------------------------------------------------------------------------

deps_detect_mpi() {
    # C compiler: explicit override, profile, or first found on PATH
    if [ -z "${DEPS_MPI_C:-}" ]; then
        if [ -n "${MPI_CC:-}" ] && [ -x "${MPI_CC}" ]; then
            DEPS_MPI_C=$MPI_CC
        elif command -v mpicc >/dev/null 2>&1; then
            DEPS_MPI_C=$(command -v mpicc)
        fi
    fi
    if [ -z "${DEPS_MPI_CXX:-}" ]; then
        if [ -n "${MPI_CXX:-}" ] && [ -x "${MPI_CXX}" ]; then
            DEPS_MPI_CXX=$MPI_CXX
        elif command -v mpicxx >/dev/null 2>&1; then
            DEPS_MPI_CXX=$(command -v mpicxx)
        elif command -v mpic++ >/dev/null 2>&1; then
            DEPS_MPI_CXX=$(command -v mpic++)
        fi
    fi
    # best-effort prefix of the MPI installation (for header/library hints)
    if [ -z "${DEPS_MPI_DIR:-}" ] && [ -n "${DEPS_MPI_CXX:-}" ]; then
        DEPS_MPI_DIR=$(dirname "$(dirname "$DEPS_MPI_CXX")")
    fi
}

# common CMake flags to make ADIOS2/openPMD find the loaded MPI
deps_mpi_cmake_flags() {
    DEPS_MPI_FLAGS=()
    if [ -n "${DEPS_MPI_C:-}" ]; then
        DEPS_MPI_FLAGS+=(-DMPI_C_COMPILER="$DEPS_MPI_C")
    fi
    if [ -n "${DEPS_MPI_CXX:-}" ]; then
        DEPS_MPI_FLAGS+=(-DMPI_CXX_COMPILER="$DEPS_MPI_CXX")
    fi
    if [ -n "${DEPS_MPI_DIR:-}" ]; then
        DEPS_MPI_FLAGS+=(-DMPI_C_HEADER_DIR="${DEPS_MPI_DIR}/include")
        DEPS_MPI_FLAGS+=(-DMPI_CXX_HEADER_DIR="${DEPS_MPI_DIR}/include")
    fi
}

# ---------------------------------------------------------------------------
# per-dependency install functions
# ---------------------------------------------------------------------------

deps_boost_build() {
    # $1 source dir, $2 install target; run through deps_build so the
    # exit status is checked, logged and honours DEPS_QUIET
    local src=$1
    local target=$2
    cd "$src" || return 1
    ./bootstrap.sh \
        --with-libraries="$DEPS_BOOST_LIBRARIES" \
        --prefix="$target" \
        CC="$DEPS_CC" CXX="$DEPS_CXX" || return 1
    ./b2 cxxflags="-std=$DEPS_CXXSTD" -j "$DEPS_JOBS" || return 1
    ./b2 install
}

deps_install_boost() {
    local key=boost
    local version
    version=$(deps_resolve_version "$key")
    local target
    target=$(deps_target "$key" "$version")
    deps_guard "$key" "$target" || return 0
    local t0=$SECONDS

    local underscored
    underscored=${version//./_}
    deps_fetch_tarball "https://archives.boost.io/release/$version/source/boost_${underscored}.tar.gz" "boost_${underscored}.tar.gz" || return 1
    local src="$DEPS_KEY_DIR/src/boost_${underscored}"
    if [ ! -d "$src" ]; then
        mkdir -p "$DEPS_KEY_DIR/src"
        tar -xzf "$DEPS_SOURCE_CACHE/boost_${underscored}.tar.gz" -C "$DEPS_KEY_DIR/src" || return 1
    fi

    deps_build "$key" deps_boost_build "$src" "$target" || return 1
    deps_stamp "$key" "$target"
    deps_record "$key" 0 $((SECONDS - t0))
}

deps_install_c_blosc2() {
    local key=c-blosc2
    local version
    version=$(deps_resolve_version "$key")
    local target
    target=$(deps_target "$key" "$version")
    deps_guard "$key" "$target" || return 0
    local t0=$SECONDS

    deps_fetch_git "https://github.com/Blosc/c-blosc2.git" "v$version" "$key" || return 1
    local src
    src=$(deps_prepare_source_copy "$key" "$(deps_git_cache_dir "$key" "v$version")")

    local build="$DEPS_KEY_DIR/build/$key"
    mkdir -p "$build"
    local prefix_hint="${DEPS_CMAKE_PREFIX_HINT:-}"
    deps_build "$key" cmake \
        -S "$src" -B "$build" \
        -DCMAKE_INSTALL_PREFIX="$target" \
        -DBUILD_TESTS=OFF \
        ${prefix_hint:+-DCMAKE_PREFIX_PATH="$prefix_hint"} \
        ${DEPS_CMAKE_EXTRA_BLOSC2:-} || return 1
    deps_build "$key" cmake --build "$build" -j "$DEPS_JOBS" || return 1
    deps_build "$key" cmake --install "$build" || return 1
    deps_stamp "$key" "$target"
    deps_record "$key" 0 $((SECONDS - t0))
}

deps_install_libpng() {
    local key=libpng
    local version
    version=$(deps_resolve_version "$key")
    local target
    target=$(deps_target "$key" "$version")
    deps_guard "$key" "$target" || return 0
    local t0=$SECONDS

    deps_fetch_tarball "https://download.sourceforge.net/libpng/libpng-$version.tar.gz" "libpng-$version.tar.gz" || return 1
    local src="$DEPS_KEY_DIR/src/libpng-$version"
    if [ ! -d "$src" ]; then
        mkdir -p "$DEPS_KEY_DIR/src"
        tar -xzf "$DEPS_SOURCE_CACHE/libpng-$version.tar.gz" -C "$DEPS_KEY_DIR/src" || return 1
    fi

    # path passed via environment (not string interpolation) so a prefix
    # containing a quote cannot break the command
    DEPS_SRC="$src" DEPS_TARGET="$target" DEPS_NJOBS="$DEPS_JOBS" \
        deps_build "$key" bash -c 'cd "$DEPS_SRC" && ./configure --prefix="$DEPS_TARGET" --enable-shared --enable-static && make -j "$DEPS_NJOBS" && make install' || return 1
    deps_stamp "$key" "$target"
    deps_record "$key" 0 $((SECONDS - t0))
}

deps_install_pngwriter() {
    local key=pngwriter
    local version
    version=$(deps_resolve_version "$key")
    local target
    target=$(deps_target "$key" "$version")
    deps_guard "$key" "$target" || return 0
    local t0=$SECONDS

    deps_fetch_git "https://github.com/pngwriter/pngwriter.git" "$version" "$key" || return 1
    local src
    src=$(deps_prepare_source_copy "$key" "$(deps_git_cache_dir "$key" "$version")")

    local build="$DEPS_KEY_DIR/build/$key"
    mkdir -p "$build"
    local prefix_hint=""
    local libpng_target
    libpng_target=$(deps_target libpng "$(deps_resolve_version libpng)")
    if [ -d "$libpng_target" ]; then
        prefix_hint="$libpng_target"
    elif [ -n "${LIBPNG_ROOT:-}" ] && [ -d "${LIBPNG_ROOT}" ]; then
        prefix_hint="$LIBPNG_ROOT"
    fi
    if [ -n "${DEPS_CMAKE_PREFIX_HINT:-}" ]; then
        prefix_hint="${prefix_hint:+$prefix_hint:}$DEPS_CMAKE_PREFIX_HINT"
    fi

    # PNGwriter 0.7.0 declares cmake_minimum_required(VERSION 2.8.12),
    # which CMake >= 3.27 rejects outright; CMAKE_POLICY_VERSION_MINIMUM=3.5
    # is the documented workaround and a no-op for older CMake.
    deps_build "$key" cmake \
        -S "$src" -B "$build" \
        -DCMAKE_INSTALL_PREFIX="$target" \
        -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
        ${prefix_hint:+-DCMAKE_PREFIX_PATH="$prefix_hint"} \
        ${DEPS_CMAKE_EXTRA_PNGWRITER:-} || return 1
    deps_build "$key" cmake --build "$build" -j "$DEPS_JOBS" || return 1
    deps_build "$key" cmake --install "$build" || return 1
    deps_stamp "$key" "$target"
    deps_record "$key" 0 $((SECONDS - t0))
}

deps_install_hdf5() {
    local key=hdf5
    local version
    version=$(deps_resolve_version "$key")
    local target
    target=$(deps_target "$key" "$version")
    deps_guard "$key" "$target" || return 0
    local t0=$SECONDS

    deps_fetch_git "https://github.com/HDFGroup/hdf5.git" "hdf5_$version" "$key" || return 1
    local src
    src=$(deps_prepare_source_copy "$key" "$(deps_git_cache_dir "$key" "hdf5_$version")")

    local build="$DEPS_KEY_DIR/build/$key"
    mkdir -p "$build"

    deps_build "$key" cmake \
        -S "$src" -B "$build" \
        -DCMAKE_INSTALL_PREFIX="$target" \
        -DHDF5_ENABLE_PARALLEL=ON \
        -DHDF5_ENABLE_FORTRAN=OFF \
        ${DEPS_MPI_C:+-DCMAKE_C_COMPILER="$DEPS_MPI_C"} \
        ${DEPS_MPI_CXX:+-DCMAKE_CXX_COMPILER="$DEPS_MPI_CXX"} \
        ${DEPS_CMAKE_PREFIX_HINT:+-DCMAKE_PREFIX_PATH="$DEPS_CMAKE_PREFIX_HINT"} \
        ${DEPS_CMAKE_EXTRA_HDF5:-} || return 1
    deps_build "$key" cmake --build "$build" -j "$DEPS_JOBS" || return 1
    deps_build "$key" cmake --install "$build" || return 1
    deps_stamp "$key" "$target"
    deps_record "$key" 0 $((SECONDS - t0))
}

deps_install_adios2() {
    local key=adios2
    local version
    version=$(deps_resolve_version "$key")
    local target
    target=$(deps_target "$key" "$version")
    deps_guard "$key" "$target" || return 0
    local t0=$SECONDS

    deps_fetch_git "https://github.com/ornladios/ADIOS2.git" "v$version" "$key" || return 1
    local src
    src=$(deps_prepare_source_copy "$key" "$(deps_git_cache_dir "$key" "v$version")")
    # perlmutter needed this patch for MPICH client/server builds
    if [ "${DEPS_ADIOS2_PATCH_CLIENT_SERVER:-0}" -eq 1 ]; then
        sed -i 's|if (ADIOS2_HAVE_MPI_CLIENT_SERVER)|if (TRUE)|' "$src/cmake/DetectOptions.cmake"
    fi

    local build="$DEPS_KEY_DIR/build/$key"
    mkdir -p "$build"
    deps_mpi_cmake_flags

    local hdf5_hint=""
    local hdf5_target
    hdf5_target=$(deps_target hdf5 "$(deps_resolve_version hdf5)")
    if [ -d "$hdf5_target" ]; then
        hdf5_hint="$hdf5_target"
    fi
    if [ -n "${DEPS_CMAKE_PREFIX_HINT:-}" ]; then
        hdf5_hint="${hdf5_hint:+$hdf5_hint:}$DEPS_CMAKE_PREFIX_HINT"
    fi

    deps_build "$key" cmake \
        -S "$src" -B "$build" \
        -DADIOS2_BUILD_EXAMPLES=OFF \
        -DCMAKE_INSTALL_PREFIX="$target" \
        -DADIOS2_USE_Fortran=OFF \
        -DADIOS2_USE_BZip2=OFF \
        -DADIOS2_USE_MPI=ON \
        -DADIOS2_USE_HDF5=ON \
        "${DEPS_MPI_FLAGS[@]}" \
        ${hdf5_hint:+-DCMAKE_PREFIX_PATH="$hdf5_hint"} \
        ${DEPS_CMAKE_EXTRA_ADIOS2:-} || return 1
    deps_build "$key" cmake --build "$build" -j "$DEPS_JOBS" || return 1
    deps_build "$key" cmake --install "$build" || return 1
    deps_stamp "$key" "$target"
    deps_record "$key" 0 $((SECONDS - t0))
}

deps_install_openpmd() {
    local key=openpmd
    local version
    version=$(deps_resolve_version "$key")
    local target
    target=$(deps_target "$key" "$version")
    deps_guard "$key" "$target" || return 0
    local t0=$SECONDS

    deps_fetch_git "https://github.com/openPMD/openPMD-api.git" "$version" "$key" || return 1
    local src
    src=$(deps_prepare_source_copy "$key" "$(deps_git_cache_dir "$key" "$version")")

    local build="$DEPS_KEY_DIR/build/$key"
    mkdir -p "$build"
    deps_mpi_cmake_flags

    # backends: use what is available (built in this run or pre-existing)
    local use_hdf5="${DEPS_OPENPMD_USE_HDF5:-}"
    local use_adios2="${DEPS_OPENPMD_USE_ADIOS2:-}"
    if [ -z "$use_hdf5" ]; then
        if deps_dep_installed hdf5 "$(deps_resolve_version hdf5)"; then
            use_hdf5=ON
        else
            use_hdf5=OFF
        fi
    fi
    if [ -z "$use_adios2" ]; then
        if deps_dep_installed adios2 "$(deps_resolve_version adios2)"; then
            use_adios2=ON
        else
            use_adios2=OFF
        fi
    fi

    local hints=""
    local hdf5_target adios2_target
    hdf5_target=$(deps_target hdf5 "$(deps_resolve_version hdf5)")
    adios2_target=$(deps_target adios2 "$(deps_resolve_version adios2)")
    if [ -d "$hdf5_target" ]; then
        hints="$hdf5_target"
    fi
    if [ -d "$adios2_target" ]; then
        hints="${hints:+$hints:}$adios2_target"
    fi
    if [ -n "${DEPS_CMAKE_PREFIX_HINT:-}" ]; then
        hints="${hints:+$hints:}$DEPS_CMAKE_PREFIX_HINT"
    fi

    deps_build "$key" cmake \
        -S "$src" -B "$build" \
        -DCMAKE_INSTALL_PREFIX="$target" \
        -DopenPMD_USE_HDF5="$use_hdf5" \
        -DopenPMD_USE_ADIOS2="$use_adios2" \
        -DBUILD_EXAMPLES=OFF \
        -DBUILD_TESTING=OFF \
        "${DEPS_MPI_FLAGS[@]}" \
        ${hints:+-DCMAKE_PREFIX_PATH="$hints"} \
        ${DEPS_CMAKE_EXTRA_OPENPMD:-} || return 1
    deps_build "$key" cmake --build "$build" -j "$DEPS_JOBS" || return 1
    deps_build "$key" cmake --install "$build" || return 1
    deps_stamp "$key" "$target"
    deps_record "$key" 0 $((SECONDS - t0))
}

deps_install_fftw3() {
    local key=fftw3
    local version
    version=$(deps_resolve_version "$key")
    local target
    target=$(deps_target "$key" "$version")
    deps_guard "$key" "$target" || return 0
    local t0=$SECONDS

    deps_fetch_tarball "https://www.fftw.org/fftw-$version.tar.gz" "fftw-$version.tar.gz" || return 1
    local src="$DEPS_KEY_DIR/src/fftw-$version"
    if [ ! -d "$src" ]; then
        mkdir -p "$DEPS_KEY_DIR/src"
        tar -xzf "$DEPS_SOURCE_CACHE/fftw-$version.tar.gz" -C "$DEPS_KEY_DIR/src" || return 1
    fi

    # path passed via environment (not string interpolation) so a prefix
    # containing a quote cannot break the command
    DEPS_SRC="$src" DEPS_TARGET="$target" DEPS_NJOBS="$DEPS_JOBS" \
        DEPS_FFTW_EXTRA="${DEPS_FFTW_CONFIGURE_EXTRA:-}" \
        deps_build "$key" bash -c 'cd "$DEPS_SRC" && ./configure --prefix="$DEPS_TARGET" $DEPS_FFTW_EXTRA && make -j "$DEPS_NJOBS" && make install' || return 1
    deps_stamp "$key" "$target"
    deps_record "$key" 0 $((SECONDS - t0))
}

# human-readable source for --list / documentation
deps_source_desc() {
    local key=$1
    local version
    version=$(deps_resolve_version "$key")
    case $key in
    boost)
        printf 'tarball: archives.boost.io/release/%s/source/boost_%s.tar.gz' "$version" "${version//./_}"
        ;;
    c-blosc2)
        printf 'git: github.com/Blosc/c-blosc2 @ v%s' "$version"
        ;;
    libpng)
        printf 'tarball: download.sourceforge.net/libpng/libpng-%s.tar.gz' "$version"
        ;;
    pngwriter)
        printf 'git: github.com/pngwriter/pngwriter @ %s' "$version"
        ;;
    hdf5)
        printf 'git: github.com/HDFGroup/hdf5 @ hdf5_%s' "$version"
        ;;
    adios2)
        printf 'git: github.com/ornladios/ADIOS2 @ v%s' "$version"
        ;;
    openpmd)
        printf 'git: github.com/openPMD/openPMD-api @ %s' "$version"
        ;;
    fftw3)
        printf 'tarball: www.fftw.org/fftw-%s.tar.gz' "$version"
        ;;
    esac
}

# ---------------------------------------------------------------------------
# environment file (managed mode)
# ---------------------------------------------------------------------------

deps_env_set() {
    # $1 variable, $2 literal value
    DEPS_ENV_LINES+=("export $1=\"$2\"")
}

deps_env_path_append() {
    # $1 variable, rest: directories to prepend
    # emits: export VAR="dir1:dir2${VAR:+:$VAR}" (evaluated when sourced)
    local var=$1
    shift
    local dirs=""
    local d
    for d in "$@"; do
        dirs+="${dirs:+:}$d"
    done
    DEPS_ENV_LINES+=("export ${var}=\"${dirs}\${${var}:+:\${${var}}}\"")
}

deps_write_env_file() {
    local key_dir="$DEPS_INSTALL_ROOT/$DEPS_KEY"
    local env_file="$key_dir/picongpu-deps.env"
    DEPS_ENV_LINES=(
        "# generated by picongpu-deps.sh (DRAFT) - do not edit"
        "# toolchain key: $DEPS_KEY"
        "# date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    )
    local key version target root_var
    for key in "${DEPS_KEYS[@]}"; do
        version=$(deps_resolve_version "$key")
        # cluster mode -> the profile's *_ROOT; managed mode -> the
        # toolchain-keyed prefix. The env file is the union of both, so
        # managed-mode installs stay visible even when the profile exports
        # some (but not all) *_ROOT variables (the mixed cluster case).
        target=$(deps_target "$key" "$version")
        [ -d "$target" ] || continue
        root_var="${DEPS_ROOT_VAR[$key]}"
        deps_env_set "$root_var" "$target"
        case $key in
        boost)
            deps_env_path_append CMAKE_PREFIX_PATH "$target/lib/cmake"
            deps_env_path_append LD_LIBRARY_PATH "$target/lib"
            ;;
        fftw3)
            deps_env_set FFTW_ROOT "$target"
            deps_env_path_append CMAKE_PREFIX_PATH "$target"
            deps_env_path_append PKG_CONFIG_PATH "$target/lib/pkgconfig" "$target/lib64/pkgconfig"
            deps_env_path_append LD_LIBRARY_PATH "$target/lib" "$target/lib64"
            ;;
        *)
            deps_env_path_append CMAKE_PREFIX_PATH "$target"
            deps_env_path_append LD_LIBRARY_PATH "$target/lib" "$target/lib64"
            ;;
        esac
    done
    printf '%s\n' "${DEPS_ENV_LINES[@]}" >"$env_file"
    # stable pointer so build/run scripts do not need to know the key;
    # warn when it is re-pointed at a different toolchain (last-writer-wins
    # is visible, not silent)
    local current="$DEPS_INSTALL_ROOT/current.env"
    if [ -f "$current" ]; then
        local old_key
        old_key=$(grep '^# toolchain key:' "$current" | head -n1 | cut -d' ' -f4 || true)
        if [ -n "$old_key" ] && [ "$old_key" != "$DEPS_KEY" ]; then
            deps_warn "$current now points at toolchain key $DEPS_KEY (it held $old_key); all consumers of current.env switch to this toolchain's prefixes"
        fi
    fi
    cp "$env_file" "$current"
    deps_log "wrote $env_file (and $current)"
}

# ---------------------------------------------------------------------------
# providers
# ---------------------------------------------------------------------------

deps_provider_source() {
    local rc=0
    local done_count=0
    local key fn t0
    for key in "${DEPS_KEYS[@]}"; do
        deps_dep_requested "$key" || continue
        fn="${DEPS_FN[$key]:-}"
        if [ -z "$fn" ] || [ "$(type -t "$fn" 2>/dev/null)" != "function" ]; then
            deps_record "$key" 1 0
            deps_warn "$key: internal error, no install function registered (DEPS_FN[$key]='$fn'); aborting"
            rc=1
            break
        fi
        t0=$SECONDS
        if "$fn"; then
            done_count=$((done_count + 1))
        else
            deps_record "$key" 1 $((SECONDS - t0))
            deps_warn "$key: build failed (see $DEPS_KEY_DIR/logs/$key.log); aborting remaining dependencies"
            rc=1
            break
        fi
    done
    deps_write_summary
    if [ "$done_count" -eq 0 ] && [ "$rc" -eq 0 ]; then
        deps_warn "no dependency matched DEPS_ONLY='${DEPS_ONLY:-}'; valid keys: ${DEPS_KEYS[*]}"
        return 1
    fi
    if [ "$rc" -ne 0 ]; then
        return "$rc"
    fi
    # hand the resulting prefixes to the build via an environment file:
    # the union of the profile's cluster-mode *_ROOT hints and the
    # managed-mode prefixes, so managed installs are visible even in
    # mixed profiles (which export some but not all *_ROOT variables)
    deps_write_env_file
}

deps_provider_modules() {
    # nothing to install: just verify the prefixes a profile is supposed to
    # expose actually contain what CMake needs
    deps_log "provider 'modules': verifying existing installations (nothing will be built)"
    local key version target root_var
    local rc=0
    for key in "${DEPS_KEYS[@]}"; do
        deps_dep_requested "$key" || continue
        version=$(deps_resolve_version "$key")
        root_var="${DEPS_ROOT_VAR[$key]}"
        if [ -z "${!root_var:-}" ]; then
            deps_warn "$key: $root_var is not set; is the profile/preset loaded?"
            rc=1
            continue
        fi
        target="${!root_var}"
        if [ ! -d "$target" ]; then
            deps_warn "$key: $root_var=$target does not exist"
            rc=1
        else
            deps_log "$key: OK ($target)"
        fi
    done
    return $rc
}

deps_provider_conda() {
    deps_warn "provider 'conda' is a DRAFT: it activates $DEPS_CONDA_ENV and points the hints at the environment prefix."
    deps_warn "NOTE: PNGwriter is NOT on conda-forge; build it separately with DEPS_ONLY=pngwriter (provider source)."
    if ! command -v conda >/dev/null 2>&1; then
        deps_die "conda not found on PATH"
    fi
    # shellcheck disable=SC1091
    source "$(conda info --base)/etc/profile.d/conda.sh"
    conda activate "${DEPS_CONDA_ENV:?set DEPS_CONDA_ENV to the conda environment name}"
    DEPS_INSTALL_ROOT="$CONDA_PREFIX"
    DEPS_KEY="conda-${DEPS_CONDA_ENV}"
    # all conda packages share one prefix; write a single-prefix env file
    DEPS_ENV_LINES=(
        "# generated by picongpu-deps.sh (DRAFT), provider=conda, env: ${DEPS_CONDA_ENV}"
    )
    deps_env_set CONDA_PREFIX "$CONDA_PREFIX"
    deps_env_path_append CMAKE_PREFIX_PATH "$CONDA_PREFIX"
    deps_env_path_append LD_LIBRARY_PATH "$CONDA_PREFIX/lib"
    deps_env_path_append PKG_CONFIG_PATH "$CONDA_PREFIX/lib/pkgconfig"
    printf '%s\n' "${DEPS_ENV_LINES[@]}" >"$CONDA_PREFIX/picongpu-deps.env"
    cp "$CONDA_PREFIX/picongpu-deps.env" "$CONDA_PREFIX/current.env" 2>/dev/null || true
    deps_log "activated conda env '${DEPS_CONDA_ENV}' ($CONDA_PREFIX)"
}

deps_provider_container() {
    deps_die "provider 'container' is not implemented in this draft (see TASK-12-FINDINGS.md; connects with the EFP container path)"
}

# ---------------------------------------------------------------------------
# summary
# ---------------------------------------------------------------------------

deps_write_summary() {
    if [ "${#DEPS_SUMMARY[@]}" -eq 0 ]; then
        return 0
    fi
    deps_log "---------------- summary ----------------"
    local entry
    for entry in "${DEPS_SUMMARY[@]}"; do
        local key rc secs
        IFS='|' read -r key rc secs <<<"$entry"
        if [ "$rc" -eq 0 ]; then
            deps_log "$key: built in ${secs}s"
        else
            deps_log "$key: FAILED after ${secs}s"
        fi
    done
    deps_log "------------------------------------------"
    # clear so the EXIT-trap call in the main script does not print twice
    DEPS_SUMMARY=()
}
