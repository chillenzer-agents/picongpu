"""
This file is part of PIConGPU.
Copyright 2021-2025 PIConGPU contributors
Authors: Hannes Troepgen, Brian Edward Marre, Richard Pausch, Julian Lenz
License: GPLv3+
"""

import enum
from typing import Annotated

from pydantic import AfterValidator, BeforeValidator, BaseModel, Field, PlainSerializer, model_validator
from typing_extensions import Self

from .rendering import RenderedObject
from .validation import all_positive
from .vector import deserialise_grid_dist, deserialise_vec, serialise_grid_dist, serialise_vec


class BoundaryCondition(enum.Enum):
    """
    Boundary Condition of PIConGPU

    Defines how particles that pass the simulation bounding box are treated.

    TODO: implement the other methods supported by PIConGPU
    (reflecting, thermal)
    """

    PERIODIC = 1
    ABSORBING = 2

    def get_cfg_str(self) -> str:
        """
        Get string equivalent for cfg files
        :return: string for --periodic
        """
        literal_by_boundarycondition = {
            BoundaryCondition.PERIODIC: "1",
            BoundaryCondition.ABSORBING: "0",
        }
        return literal_by_boundarycondition[self]


Vec3_float = Annotated[tuple[float, float, float], BeforeValidator(deserialise_vec), PlainSerializer(serialise_vec)]
Vec3_int = Annotated[tuple[int, int, int], BeforeValidator(deserialise_vec), PlainSerializer(serialise_vec)]


def grid_dist_validate(grid_dist):
    if grid_dist is None:
        return None
    if all_positive(sum(grid_dist, [])):
        return grid_dist


class Grid3D(BaseModel, RenderedObject):
    """
    PIConGPU 3 dimensional (cartesian) grid

    Defined by the dimensions of each cell and the number of cells per axis.

    The bounding box is implicitly given as TODO.
    """

    cell_size: Annotated[Vec3_float, AfterValidator(lambda x: all_positive(x, field="cell_size"))] = Field(
        alias="cell_size_si"
    )
    """Width of individual cell in each direction"""

    cell_cnt: Annotated[Vec3_int, AfterValidator(lambda x: all_positive(x, field="cell_cnt"))]
    """total number of cells in each direction"""

    boundary_condition: Annotated[
        tuple[BoundaryCondition, BoundaryCondition, BoundaryCondition],
        PlainSerializer(lambda x: serialise_vec(map(BoundaryCondition.get_cfg_str, x)), return_type=dict),
    ]
    """behavior towards particles crossing each boundary"""

    gpu_cnt: Annotated[Vec3_int, AfterValidator(lambda x: all_positive(x, field="gpu_cnt"))] = Field(
        (1, 1, 1), alias="n_gpus"
    )
    """number of GPUs in x y and z direction as 3-integer tuple"""

    grid_dist: Annotated[
        tuple[list[int], list[int], list[int]] | None,
        BeforeValidator(deserialise_grid_dist),
        PlainSerializer(serialise_grid_dist),
        AfterValidator(grid_dist_validate),
    ] = None
    """distribution of grid cells to GPUs for each axis"""

    # strictly positive on purpose: like cell_size/cell_cnt/gpu_cnt a super cell is a per-axis
    # cell count, and a non-positive value would emit invalid C++ (picmi already enforces >= 1)
    super_cell_size: Annotated[Vec3_int, AfterValidator(lambda x: all_positive(x, field="super_cell_size"))]
    """size of super cell in x y and z direction as 3-integer tuple in cells"""

    @model_validator(mode="after")
    def check(self) -> Self:
        """serialized representation provided for RenderedObject"""
        if self.grid_dist is not None:
            assert sum(self.grid_dist[0]) == self.cell_cnt[0], "sum of grid_dists in x must be equal to number_of_cells"
            assert sum(self.grid_dist[1]) == self.cell_cnt[1], "sum of grid_dists in y must be equal to number_of_cells"
            assert sum(self.grid_dist[2]) == self.cell_cnt[2], "sum of grid_dists in z must be equal to number_of_cells"

        return self
