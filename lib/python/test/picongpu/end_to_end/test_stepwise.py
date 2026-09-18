"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: chillenzer-agents
License: GPLv3+

End-to-end test for restart-aware stepwise running (issue #85).

Runs 2 time steps **once via `simulation.run()`** (the whole ``[0, 2)`` as one
shot, batched/submitted) and **once via `simulation.step()` twice** (two chunks
``[0, 1)`` and ``[1, 2)`` that resume from a checkpoint), and asserts the
**last checkpoint is byte-identical** between the two: both reach the same
simulation state at step 2, so the checkpoint written at step 2 must match.

NOTE: this test compiles and runs PIConGPU on a GPU and therefore only runs in
CI (it is not part of the in-container quick suite). It lives with the other
compiled end-to-end tests.

The ``run()`` path is batched (a background job), so it is gathered with
``gather_results``. The ``step()`` path runs each chunk in the *foreground*
(synchronously), so by the time ``step()`` returns the chunk has finished and
no async gathering is required.
"""

import filecmp
import logging
from pathlib import Path

from picongpu import rc_params
from picongpu.picmi import Cartesian3DGrid, ElectromagneticSolver, Simulation
from picongpu.picmi.diagnostics import Checkpoint, TimeStepSpec

from .arbitrary_parameters import gather_results, directory_in_home

logging.basicConfig(level=logging.INFO)


def _make_sim(max_steps=2):
    # A user checkpoint covering the final step (2) so that *both* run() and
    # step() produce a checkpoint at step 2 to compare. The user's period does
    # NOT cover intermediate chunk boundaries, so step() auto-schedules those
    # (exercising the auto-checkpoint + restart path).
    return Simulation(
        time_step_size=1.0e-15,
        max_steps=max_steps,
        solver=ElectromagneticSolver(
            method="Yee",
            cfl=0.5,
            grid=Cartesian3DGrid(
                number_of_cells=[32, 32, 16],
                lower_bound=[0, 0, 0],
                upper_bound=[32.0, 32.0, 16.0],
                lower_boundary_conditions=["open", "open", "periodic"],
                upper_boundary_conditions=["open", "open", "periodic"],
            ),
        ),
        diagnostics=[Checkpoint(period=TimeStepSpec[2], directory="checkpoints", file="checkpoint")],
    )


def _run_dir_for(sim):
    runner = sim.picongpu_get_runner()
    if "rosi-hzdr" in rc_params.get("preset", "bash"):
        # On ROSI the tmp directories are inaccessible to the compute nodes.
        runner.setup_dir = directory_in_home() / "setup"
        runner.run_dir = directory_in_home() / "run"
    return runner.run_dir


def _checkpoint_files(run_dir: Path) -> list[Path]:
    """All checkpoint data files under the run's shared simOutput/checkpoints."""
    checkpoint_dir = run_dir / "simOutput" / "checkpoints"
    if not checkpoint_dir.is_dir():
        return []
    return sorted(p for p in checkpoint_dir.rglob("*") if p.is_file() and p.name != "checkpoints.txt")


def _step2_checkpoint(cps: list[Path]) -> Path:
    """The step-2 checkpoint file (the openPMD infix encodes the step)."""
    matches = [p for p in cps if "000002" in p.name]
    assert matches, f"no step-2 checkpoint among {[p.name for p in cps]}"
    return matches[-1]


def test_stepwise_matches_full_run_checkpoint():
    # Case 1: the whole [0, 2) range as a single run() (batched, async).
    sim_run = _make_sim()
    run_dir_run = _run_dir_for(sim_run)
    sim_run.run()
    gather_results(run_dir_run)

    # Case 2: the same [0, 2) range as two step() chunks (foreground, sync).
    sim_step = _make_sim()
    run_dir_step = _run_dir_for(sim_step)
    sim_step.step(nsteps=1)  # chunk [0, 1): auto-checkpoint at 1, no restart yet
    sim_step.step(nsteps=1)  # chunk [1, 2): restart at 1, checkpoint at 2

    # Both runs reached step 2 (the user's checkpoint period fired).
    assert _checkpoint_files(run_dir_run), "run() produced no checkpoint"
    assert _checkpoint_files(run_dir_step), "step() produced no checkpoint"

    # The last (step-2) checkpoint must be byte-identical: the same simulation
    # state reached by two different execution paths.
    assert filecmp.cmp(
        _step2_checkpoint(_checkpoint_files(run_dir_run)),
        _step2_checkpoint(_checkpoint_files(run_dir_step)),
        shallow=False,
    ), (
        "the last (step-2) checkpoint differs between run() and step(); "
        "stepwise running must reproduce the same simulation state"
    )
