"""
This file is part of PIConGPU.
Copyright 2021-2024 PIConGPU contributors
Authors: Hannes Troepgen, Brian Edward Marre
License: GPLv3+
"""

from functools import partial
from operator import gt, le

import numpy as np
import picmistandard
from pydantic import BaseModel, Field, computed_field, field_validator

from ..pypicongpu.species.operation.layout import OnePosition as PyPIConGPU_OnePosition
from ..pypicongpu.species.operation.layout import Quiet, Random


class PseudoRandomLayout(picmistandard.PICMI_PseudoRandomLayout):
    n_macroparticles_per_cell: int = Field(
        gt=0,
        description="Number of macroparticles to load per cell. Either this argument or n_macroparticles "
        "should be supplied (not both).",
    )
    # PIConGPU can't handle the following separately:
    n_macroparticles: None = Field(
        None,
        description="Not supported by PIConGPU: the particle count is set per cell via "
        "n_macroparticles_per_cell, so n_macroparticles must be None.",
    )
    seed: None = Field(
        None,
        description="Not supported by PIConGPU: the pseudo-random number generator seed cannot be chosen, "
        "so seed must be None.",
    )
    grid: None = Field(
        None,
        description="Not supported by PIConGPU: the underlying grid is always used, so grid must be None.",
    )

    def get_as_pypicongpu(self):
        return Random(ppc=self.n_macroparticles_per_cell)


class GriddedLayout(picmistandard.PICMI_GriddedLayout):
    n_macroparticles_per_cell: list[int] = Field(
        [0],
        init_var=False,
        description="Number of particles per cell along each axis (one entry per grid dimension). "
        "In PIConGPU this field is typed as a plain list of ints (the standard's broadcast "
        "validation is not re-applied).",
    )

    def get_as_pypicongpu(self):
        return Quiet(ppc=np.prod(self.n_macroparticles_per_cell), n_points=self.n_macroparticles_per_cell)

    @computed_field
    def in_cell_offsets(self) -> np.ndarray:
        return (np.mgrid[*map(slice, self.n_macroparticles_per_cell)] + 0.5).reshape(
            len(self.n_macroparticles_per_cell), -1
        ).T / self.n_macroparticles_per_cell


class OnePositionLayout(BaseModel):
    n_macroparticles_per_cell: int = Field(gt=0, description="Number of particles per cell")
    in_cell_offset: tuple[float, ...] = Field(
        (0.0, 0.0, 0.0),
        description="Offset to cell origin where the particles are placed in units of cell size (between 0 and 1). "
        "Two components for a 2D grid, three for a 3D grid (the third, z, is ignored in 2D3V).",
    )
    grid: None = None

    @field_validator("in_cell_offset", mode="after")
    @classmethod
    def _validate_in_cell_offset(cls, in_cell_offset):
        if len(in_cell_offset) not in (2, 3):
            raise ValueError(
                f"in_cell_offset must have 2 (2D) or 3 (3D) components. You gave {in_cell_offset=} with {len(in_cell_offset)}."
            )
        if not (all(map(partial(le, 0.0), in_cell_offset)) and all(map(partial(gt, 1.0), in_cell_offset))):
            raise ValueError(f"All of in_cell_offset must be between 0 and 1. You gave: {in_cell_offset=}.")
        return in_cell_offset

    def get_as_pypicongpu(self):
        return PyPIConGPU_OnePosition(ppc=self.n_macroparticles_per_cell, in_cell_offset=self.in_cell_offset)


AnyLayout = PseudoRandomLayout | GriddedLayout | OnePositionLayout
