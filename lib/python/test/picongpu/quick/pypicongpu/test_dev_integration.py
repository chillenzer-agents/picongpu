"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: chillenzer-agents
License: GPLv3+

Round-trip integration regressions that appear when the serialisation work is
combined with the 2D grids / extra solvers / plugins that landed on ``dev``
after the serialisation branches were cut.
"""

from datetime import timedelta

from pydantic import TypeAdapter

from picongpu.pypicongpu.customuserinput import CustomUserInput
from picongpu.pypicongpu.field_solver import (
    AnySolver,
    ArbitraryOrderFDTDSolver,
    CKCSolver,
    LeheSolver,
    NoneSolver,
    YeeSolver,
)
from picongpu.pypicongpu.grid import AnyGrid, BoundaryCondition, Grid2D, Grid3D
from picongpu.pypicongpu.simulation import Simulation


def test_every_solver_member_discriminates():
    # dev added CKC/None/ArbitraryOrderFDTD to AnySolver after task-07 branched;
    # without the type_* discriminator each collapsed to YeeSolver on reload.
    for member in (YeeSolver(), LeheSolver(), CKCSolver(), NoneSolver()):
        dumped = member.model_dump(mode="json")
        picked = TypeAdapter(AnySolver).validate_python(dumped)
        assert type(picked) is type(member), (type(member).__name__, dumped, type(picked).__name__)
    ao = ArbitraryOrderFDTDSolver(neighbors=2)
    assert type(TypeAdapter(AnySolver).validate_python(ao.model_dump(mode="json"))) is ArbitraryOrderFDTDSolver


def test_grid_3d_and_2d_are_distinguishable():
    g3 = Grid3D(
        cell_size_si=(1e-6, 1e-6, 1e-6),
        cell_cnt=(16, 16, 16),
        boundary_condition=(BoundaryCondition.PERIODIC,) * 3,
        n_gpus=(1, 1, 1),
        super_cell_size=(8, 8, 4),
    )
    g2 = Grid2D(
        cell_size_si=(1e-6, 1e-6),
        cell_depth_si=1e-6,
        cell_cnt=(16, 16),
        boundary_condition=(BoundaryCondition.PERIODIC,) * 2,
        n_gpus=(1, 1),
        super_cell_size=(16, 16),
    )
    for grid in (g3, g2):
        dumped = grid.model_dump(mode="json")
        picked = TypeAdapter(AnyGrid).validate_python(dumped)
        assert type(picked) is type(grid), (type(grid).__name__, dumped)


def test_custom_user_input_without_tags_round_trips():
    # an entry without tags must survive a dump/validate round trip (the merged
    # Simulation form accumulates tags=[]; the field is None | list[min_length=1]).
    entry = CustomUserInput(rendering_context={"MY_PARAM": 42})
    restored = CustomUserInput.model_validate(entry.model_dump(mode="json"))
    assert restored.model_dump(mode="json") == entry.model_dump(mode="json")
