"""
This file is part of PIConGPU.
Copyright 2021-2025 PIConGPU contributors
Authors: Hannes Troepgen, Brian Edward Marre, Richard Pausch, Julian Lenz
License: GPLv3+
"""

import enum
from typing import Annotated, Literal

from pydantic import AfterValidator, BeforeValidator, BaseModel, ConfigDict, Field, PlainSerializer, model_validator
from typing_extensions import Self

from .rendering import RenderedObject
from .units import SI


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


def serialise_vec(value) -> dict:
    return dict(zip("xyz", value))


def deserialise_vec(value):
    # accept the serialised form (dict with x/y/z keys) in addition to the
    # native tuple form, so that model_dump(mode="json") output can be
    # validated again (round-trip safety)
    if isinstance(value, dict):
        try:
            return (value["x"], value["y"], value["z"])
        except KeyError as error:
            raise ValueError(f"Expected a vector with the keys x, y, z. You gave: {value=}.") from error
    return value


Vec3_float = Annotated[
    tuple[float, float, float],
    BeforeValidator(deserialise_vec),
    PlainSerializer(serialise_vec),
]
Vec3_int = Annotated[
    tuple[int, int, int],
    BeforeValidator(deserialise_vec),
    PlainSerializer(serialise_vec),
]


def serialise_grid_dist(value) -> None | dict[Literal["x", "y", "z"], list[dict[Literal["device_cells"], int]]]:
    return (
        value
        if value is None
        else {
            "x": [{"device_cells": x} for x in value[0]],
            "y": [{"device_cells": x} for x in value[1]],
            "z": [{"device_cells": x} for x in value[2]],
        }
    )


def deserialise_grid_dist(value):
    # accept the serialised form (dict with x/y/z keys holding device_cells)
    # in addition to the native tuple-of-lists form (round-trip safety)
    if isinstance(value, dict):
        try:
            return tuple([entry["device_cells"] for entry in value[axis]] for axis in ("x", "y", "z"))
        except (KeyError, TypeError) as error:
            raise ValueError(f"Expected a serialised grid distribution. You gave: {value=}.") from error
    return value


_CFG_STR_TO_BOUNDARY = {"1": BoundaryCondition.PERIODIC, "0": BoundaryCondition.ABSORBING}


def deserialise_boundary(value):
    # accept the serialised form (dict with x/y/z keys holding the cfg string
    # "1"/"0") in addition to the native tuple-of-enum form (round-trip safety)
    if isinstance(value, dict):
        try:
            return tuple(_CFG_STR_TO_BOUNDARY[value[axis]] for axis in ("x", "y", "z"))
        except (KeyError, TypeError) as error:
            raise ValueError(f"Expected a serialised boundary condition. You gave: {value=}.") from error
    return value


def all_gt(iterable, m):
    if all(correct := [x > m for x in iterable]):
        return iterable
    else:
        message = f"{iterable=} contains values <= {m=} while all should be greater than m. Valid are the following: {correct=}."
        raise ValueError(message)


def grid_dist_validate(grid_dist):
    if grid_dist is None:
        return None
    if all_gt(sum(grid_dist, []), 0):
        return grid_dist


class Grid3D(BaseModel, RenderedObject):
    """
    PIConGPU 3 dimensional (cartesian) grid

    Defined by the dimensions of each cell and the number of cells per axis.
    The bounding box is implicitly given as `cell_size * cell_cnt`.

    C++ counterparts: include/picongpu/param/simulation.param (SI::CELL_*_SI),
    include/picongpu/param/memory.param (SuperCellSize) and
    etc/picongpu/N.cfg (device layout).

    Units policy: cell sizes in meter, cell counts and super cell sizes in
    cells (dimensionless).
    """

    # accept both the field names (as produced by model_dump) and the aliases
    # (e.g. cell_size_si) upon construction, so that serialised output can be
    # validated again (round-trip safety)
    model_config = ConfigDict(populate_by_name=True)

    cell_size: Annotated[Vec3_float, AfterValidator(lambda x: all_gt(x, 0)), SI("m")] = Field(alias="cell_size_si")
    """width of an individual cell in each direction, [m]; must be > 0 in every direction.
    C++ name: SI::CELL_{WIDTH,HEIGHT,DEPTH}_SI (simulation.param)."""

    cell_cnt: Annotated[Vec3_int, AfterValidator(lambda x: all_gt(x, 0))]
    """total number of cells in each direction, [cells]; must be >= 1 in every direction."""

    boundary_condition: Annotated[
        tuple[BoundaryCondition, BoundaryCondition, BoundaryCondition],
        BeforeValidator(deserialise_boundary),
        PlainSerializer(lambda x: serialise_vec(map(BoundaryCondition.get_cfg_str, x)), return_type=dict),
    ]
    """behavior towards particles crossing each boundary (one per axis)"""

    gpu_cnt: Annotated[Vec3_int, AfterValidator(lambda x: all_gt(x, 0))] = Field((1, 1, 1), alias="n_gpus")
    """number of GPUs in x, y and z direction as 3-integer tuple, [dimensionless]; must be >= 1."""

    grid_dist: Annotated[
        tuple[list[int], list[int], list[int]] | None,
        BeforeValidator(deserialise_grid_dist),
        PlainSerializer(serialise_grid_dist),
        AfterValidator(grid_dist_validate),
    ] = None
    """explicit distribution of grid cells to the GPUs per axis, [cells]; each entry must be > 0 and
    the entries per axis must sum to cell_cnt; None distributes the cells evenly over gpu_cnt."""

    super_cell_size: Annotated[Vec3_int, AfterValidator(lambda x: all_gt(x, 0))]
    """size of the super cell in x, y and z direction as 3-integer tuple, [cells]; must be >= 1.
    C++ name: SuperCellSize (memory.param).
    The cells per device in each direction must be a multiple of the super cell size."""

    @model_validator(mode="after")
    def check(self) -> Self:
        """cross-field invariants between cell_cnt, gpu_cnt, grid_dist and super_cell_size"""
        if self.grid_dist is not None:
            for axis, message in enumerate(
                (
                    "sum of grid_dists in x must be equal to number_of_cells",
                    "sum of grid_dists in y must be equal to number_of_cells",
                    "sum of grid_dists in z must be equal to number_of_cells",
                )
            ):
                if sum(self.grid_dist[axis]) != self.cell_cnt[axis]:
                    raise ValueError(message)
            # each device's chunk must be a multiple of the super cell size
            for axis in range(3):
                for chunk in self.grid_dist[axis]:
                    if chunk % self.super_cell_size[axis] != 0:
                        raise ValueError(
                            f"grid distribution in {'xyz'[axis]} direction must be a multiple of the super cell size. "
                            f"You gave chunk {chunk} and super_cell_size {self.super_cell_size[axis]}."
                        )
        else:
            # without an explicit distribution the grid is split evenly over the GPUs,
            # so each device's share must be a multiple of the super cell size
            for axis in range(3):
                cells = self.cell_cnt[axis]
                n_gpus = self.gpu_cnt[axis]
                super_cell = self.super_cell_size[axis]
                if (cells // n_gpus // super_cell) * n_gpus * super_cell != cells:
                    raise ValueError(
                        f"GPU- and/or super-cell-distribution in {'xyz'[axis]} direction does not match grid size: "
                        f"cell_cnt {cells} is not evenly divisible by "
                        f"gpu_cnt {n_gpus} * super_cell_size {super_cell}."
                    )
        return self
