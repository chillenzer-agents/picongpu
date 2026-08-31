"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: PIConGPU contributors
License: GPLv3+
"""

import subprocess
from pathlib import Path

from picongpu import rc_params
from picongpu.dependencies import DependenciesConfig
from picongpu.picmi import Cartesian3DGrid, ElectromagneticSolver, Simulation
from pytest import fixture, raises

REPO_ROOT = Path(__file__).resolve().parents[5]
DEPS_LIB = REPO_ROOT / "etc" / "picongpu" / "dependencies" / "picongpu-deps-lib.sh"


def test_default_is_disabled():
    assert not DependenciesConfig.from_rc_params({}).enabled
    assert not DependenciesConfig.from_rc_params({}).active


def test_enabled_source_provider():
    cfg = DependenciesConfig.from_rc_params({"dependencies": {"enabled": True}})
    assert cfg.enabled
    assert cfg.active
    assert cfg.provider == "source"


def test_provider_validation():
    with raises(ValueError, match="provider"):
        DependenciesConfig.from_rc_params({"dependencies": {"enabled": True, "provider": "spack"}})


def test_unknown_dependency_in_only():
    with raises(ValueError, match="fftw"):
        DependenciesConfig.from_rc_params({"dependencies": {"enabled": True, "only": ["fftw"]}})


def test_unknown_dependency_in_versions():
    with raises(ValueError, match="openpmx"):
        DependenciesConfig.from_rc_params({"dependencies": {"enabled": True, "versions": {"openpmx": "0.17.1"}}})


def test_unknown_key():
    with raises(ValueError, match="enabled_only"):
        DependenciesConfig.from_rc_params({"dependencies": {"enabled_only": True}})


def test_install_commands():
    cfg = DependenciesConfig.from_rc_params(
        {
            "dependencies": {
                "enabled": True,
                "jobs": 8,
                "only": ["fftw3", "pngwriter"],
                "versions": {"hdf5": "1.14.6"},
            }
        }
    )
    lines = cfg.install_commands(Path("/setup/etc/picongpu/dependencies/picongpu-deps.sh"), Path("/setup/deps"))
    joined = "\n".join(lines)
    assert 'export DEPS_PROVIDER="source"' in joined
    assert 'export DEPS_INSTALL_ROOT="/setup/deps"' in joined
    assert 'export DEPS_JOBS="8"' in joined
    assert 'export DEPS_ONLY="fftw3,pngwriter"' in joined
    assert 'export DEPS_HDF5_VERSION="1.14.6"' in joined
    assert 'bash "/setup/etc/picongpu/dependencies/picongpu-deps.sh"' in joined
    assert '. "/setup/deps/current.env"' in joined


def test_install_commands_with_prefix():
    cfg = DependenciesConfig.from_rc_params({"dependencies": {"enabled": True, "prefix": "/shared/deps"}})
    lines = cfg.install_commands(Path("/x/picongpu-deps.sh"), Path("/setup/deps"))
    joined = "\n".join(lines)
    assert 'export DEPS_INSTALL_ROOT="/shared/deps"' in joined
    assert '. "/shared/deps/current.env"' in joined


def test_non_source_provider_is_not_active():
    cfg = DependenciesConfig.from_rc_params({"dependencies": {"enabled": True, "provider": "conda"}})
    assert cfg.enabled
    assert not cfg.active


@fixture
def sim():
    number_of_cells = 32
    cell_size = 1
    sim = Simulation(
        time_step_size=17,
        max_steps=4,
        solver=ElectromagneticSolver(
            method="Yee",
            grid=Cartesian3DGrid(
                number_of_cells=[number_of_cells, number_of_cells, number_of_cells],
                lower_bound=[0, 0, 0],
                upper_bound=list(map(lambda x: number_of_cells * x, [cell_size, cell_size, cell_size])),
                # required, otherwise won't spawn
                lower_boundary_conditions=["open", "open", "periodic"],
                upper_boundary_conditions=["open", "open", "periodic"],
            ),
        ),
    )
    sim.picongpu_get_runner().generate()
    return sim


def test_build_script_unchanged_by_default(sim):
    content = sim.picongpu_get_runner().build_script_path.read_text()
    assert "pic-build $@" in content
    assert "DEPS_" not in content
    assert "current.env" not in content


def test_build_script_with_dependencies_enabled(sim):
    runner = sim.picongpu_get_runner()
    with rc_params.set_temporarily(**{"dependencies": {"enabled": True, "only": ["pngwriter"], "jobs": 4}}):
        runner.generate_build_command()
        content = runner.build_script_path.read_text()
    assert "pic-build $@" in content
    assert 'DEPS_ONLY="pngwriter"' in content
    assert 'DEPS_JOBS="4"' in content
    assert "picongpu-deps.sh" in content
    assert "current.env" in content


def test_run_scripts_get_dependency_env_when_enabled(sim):
    runner = sim.picongpu_get_runner()
    with rc_params.set_temporarily(**{"dependencies": {"enabled": True}}):
        runner.generate_prepare_submission_command()
        runner.generate_submission_command()
        prepare = runner.prepare_submission_script_path.read_text()
        submit = runner.submission_script_path.read_text()
    assert "current.env" in prepare
    assert "current.env" in submit


def test_run_scripts_unchanged_by_default(sim):
    prepare = sim.picongpu_get_runner().prepare_submission_script_path.read_text()
    submit = sim.picongpu_get_runner().submission_script_path.read_text()
    assert "current.env" not in prepare
    assert "current.env" not in submit


def test_build_script_warns_for_unwired_provider(sim):
    # enabled + a provider that the generated scripts do not wire in yet
    # must be visible, not a silent no-op
    runner = sim.picongpu_get_runner()
    with rc_params.set_temporarily(**{"dependencies": {"enabled": True, "provider": "conda"}}):
        runner.generate_build_command()
        content = runner.build_script_path.read_text()
    assert "not wired into the generated scripts yet" in content


def test_provider_dispatch_covers_all_keys():
    # regression test for the key->function lookup: "deps_install_$key"
    # can never match a key containing a dash (c-blosc2), so the mapping
    # must be explicit and complete for every key
    code = r"""
        set -euo pipefail
        source "$1"
        for key in "${DEPS_KEYS[@]}"; do
            fn="${DEPS_FN[$key]:-}"
            if [ -z "$fn" ] || [ "$(type -t "$fn" 2>/dev/null)" != "function" ]; then
                echo "no install function for key: $key (fn='$fn')" >&2
                exit 1
            fi
        done
    """
    result = subprocess.run(["bash", "-c", code, "bash", str(DEPS_LIB)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_provider_loop_records_failure_and_stops(tmp_path):
    # a failing dependency must be reported in the summary, must not be
    # stamped as installed, and must abort the remaining dependencies
    code = r"""
        set -euo pipefail
        source "$1"
        DEPS_KEY_DIR="$2"
        mkdir -p "$DEPS_KEY_DIR/logs"
        DEPS_ONLY="boost,c-blosc2,libpng"
        deps_install_boost() { deps_record boost 0 0; }
        deps_install_c_blosc2() { return 1; }
        deps_install_libpng() { echo "SHOULD-NOT-REACH-LIBPNG" >&2; return 0; }
        rc=0
        deps_provider_source || rc=$?
        echo "RC=$rc"
    """
    key_dir = tmp_path / "key1"
    result = subprocess.run(["bash", "-c", code, "bash", str(DEPS_LIB), str(key_dir)], capture_output=True, text=True)
    assert "RC=1" in result.stdout
    assert "boost: built in" in result.stdout
    assert "c-blosc2: FAILED after" in result.stdout
    assert "SHOULD-NOT-REACH-LIBPNG" not in result.stderr
    assert not list(tmp_path.rglob(".picongpu-deps.stamp"))


def test_openpmd_configure_is_pointed_at_built_targets(tmp_path):
    # openpmd's CMake must be given HDF5_ROOT/ADIOS2_ROOT (the same vars
    # current.env exports to the consumer) when the hdf5/adios2 targets
    # exist: our HDF5 build's config file re-runs find_package(MPI)
    # internally, which fails under openPMD's reduced MPI component set
    # (CXX only, MPI_CXX_SKIP_MPICXX), and without HDF5_ROOT the
    # FindHDF5 module-mode fallback misses the parallel build on recent
    # CMake (verified: CMake 4.3).
    code = r"""
        set -euo pipefail
        source "$1"
        DEPS_KEY="key1"
        DEPS_INSTALL_ROOT="$2"
        DEPS_KEY_DIR="$2/key1"
        DEPS_SOURCE_CACHE="$2/sources"
        DEPS_JOBS=1
        mkdir -p "$DEPS_KEY_DIR/logs" "$DEPS_KEY_DIR/hdf5-1.14.6" "$DEPS_KEY_DIR/adios2-2.11.0"
        deps_fetch_git() { :; }
        deps_prepare_source_copy() { printf '%s' "$2"; }
        deps_mpi_cmake_flags() { DEPS_MPI_FLAGS=(); }
        deps_build() { printf '%s\n' "$*" >> "$DEPS_KEY_DIR/deps_build.log"; }
        deps_guard() { :; }
        deps_stamp() { :; }
        deps_install_openpmd
        grep -q "HDF5_ROOT=$DEPS_KEY_DIR/hdf5-1.14.6" "$DEPS_KEY_DIR/deps_build.log"
        grep -q "ADIOS2_ROOT=$DEPS_KEY_DIR/adios2-2.11.0" "$DEPS_KEY_DIR/deps_build.log"
    """
    result = subprocess.run(["bash", "-c", code, "bash", str(DEPS_LIB), str(tmp_path)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
