"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: PIConGPU contributors
License: GPLv3+
"""

from pathlib import Path

from picongpu import rc_params
from picongpu.dependencies import DependenciesConfig
from picongpu.picmi import Cartesian3DGrid, ElectromagneticSolver, Simulation
from pytest import fixture, raises


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
        DependenciesConfig.from_rc_params(
            {"dependencies": {"enabled": True, "versions": {"openpmx": "0.17.1"}}}
        )


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
