"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

import json

from cwltool.context import RuntimeContext
from cwltool.factory import Factory, WorkflowStatus
from picongpu.picmi import Cartesian3DGrid, ElectromagneticSolver, Simulation
from picongpu.pypicongpu.runner import PicBuildFlags, TBGFlags
from pytest import fixture, raises


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


@fixture
def workflow_definition_path(sim):
    return sim.picongpu_get_runner().workflow_definition_path


@fixture
def workflow_input(sim):
    with sim.picongpu_get_runner().workflow_input_path.open("r") as file:
        return json.load(file)


def test_validate_workflow(workflow_definition_path, workflow_input):
    # Couldn't have come up with a stranger interface:
    # The `validate_only` mode of the factory uses an exception to shortcircuit apparently.
    # Well, in this case "success" means:
    with raises(WorkflowStatus, match="Completed ValidationSuccess"):
        Factory(runtime_context=RuntimeContext(kwargs={"validate_only": True})).make(str(workflow_definition_path))(
            **workflow_input
        )


def test_workflow_input_accepts_flag_names_and_aliases(workflow_definition_path, sim):
    runner = sim.picongpu_get_runner()
    for build_flags, run_flags in [
        (
            PicBuildFlags(cmake_build_system="Ninja"),
            TBGFlags(project_path=runner.setup_dir, cfg_file="my.cfg", overwrite_vars=["A=1", "B=2"]),
        ),
        (
            PicBuildFlags(G="Ninja"),
            TBGFlags(project_path=runner.setup_dir, cfg="my.cfg", o=["A=1", "B=2"]),
        ),
    ]:
        runner.generate_workflow_input(build_flags=build_flags, run_flags=run_flags)
        with runner.workflow_input_path.open("r") as file:
            workflow_input = json.load(file)
        assert workflow_input["build_cmake_build_system"] == "Ninja"
        assert workflow_input["run_cfg_file"] == "my.cfg"
        assert workflow_input["run_overwrite_vars"] == json.dumps(["A=1", "B=2"])
        with raises(WorkflowStatus, match="Completed ValidationSuccess"):
            Factory(runtime_context=RuntimeContext(kwargs={"validate_only": True})).make(str(workflow_definition_path))(
                **workflow_input
            )
