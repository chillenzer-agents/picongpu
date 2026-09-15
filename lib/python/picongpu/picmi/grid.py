"""
This file is part of PIConGPU.
Copyright 2021-2025 PIConGPU contributors
Authors: Hannes Troepgen, Brian Edward Marre, Richard Pausch, Julian Lenz
License: GPLv3+
"""

from typing import Annotated, Sequence
import picmistandard
from pydantic import AfterValidator, BeforeValidator, Field, computed_field, model_validator

from ..pypicongpu import grid, util
from ..pypicongpu.species.species_boundary import SpeciesParticleBoundary
from .copy_attributes import converts_to
from . import particle_boundary
from .particle_boundary import PICONGPU_PARTICLE_BOUNDARY_CONDITION_BY_PICMI_ID, ParticleBoundary


def _normalise_type(kw, key, t):
    kw[key] = tuple(t(bound) for bound in kw[key])
    return kw


PICONGPU_BOUNDARY_CONDITION_BY_PICMI_ID = {
    "open": grid.BoundaryCondition.ABSORBING,
    "periodic": grid.BoundaryCondition.PERIODIC,
}


def _reject_bool_n_gpus(n_gpus):
    # bool is an int subclass, so without this explicit check pydantic's lax
    # int coercion would silently turn True/False into 1/0 GPUs.
    if isinstance(n_gpus, bool):
        raise ValueError(
            f"picongpu_n_gpus must be a positive int or a sequence of positive ints, not a bool. You gave {n_gpus!r}."
        )
    return n_gpus


def _normalise_n_gpus(n_gpus, n_dimensions: int):
    """Normalise the accepted forms of ``picongpu_n_gpus`` into an ``n_dimensions``-tuple.

    Accepted forms:
      * ``None`` -> single-GPU default ``(1, ..., 1)``
      * a bare positive int ``N`` -> parallelise in y: ``N`` in the second
        slot, 1 everywhere else (e.g. ``(1, N, 1)`` in 3D, ``(1, N)`` in 2D)
      * a 1-element sequence ``[N]`` / ``(N,)`` -> same as a bare int
      * an ``n_dimensions``-element sequence -> unchanged

    Everything else (empty, wrong-length or non-positive sequences, ...) is
    rejected. Note that pydantic's lax mode coerces whole-number floats to int
    (``4.0`` -> ``4``) before this runs, so integral floats are accepted as the
    equivalent int on purpose.
    """
    picongpu_n_gpus = n_gpus
    # a bare integer is interpreted as a single number of GPUs parallelized in y
    if n_gpus is None:
        n_gpus = tuple([1] * n_dimensions)
    elif isinstance(n_gpus, int):
        n_gpus = tuple(n_gpus if i == 1 else 1 for i in range(n_dimensions))
    else:
        n_gpus = tuple(n_gpus)

    if len(n_gpus) == 1:
        n_gpus = tuple(n_gpus[0] if i == 1 else 1 for i in range(n_dimensions))

    if len(n_gpus) != n_dimensions:
        raise ValueError(
            f"The given number of gpus could not be mapped to a {n_dimensions}-component list of integers. "
            f"You gave {picongpu_n_gpus} and we interpreted this as {n_gpus=}."
        )

    if any(map(lambda x: x <= 0, n_gpus)):
        raise ValueError(
            f"Number of gpus must be positive integer(s). "
            f"You gave {picongpu_n_gpus=} and we interpreted this as {n_gpus=}."
        )

    return n_gpus


def _check_cartesian_grid(self, dim_name):
    _check_lower_bound_is_zero(self)
    _check_boundary_conditions(self, dim_name)
    _reject_unsupported_cartesian_grid_features(self)
    _check_grid_distribution(self, dim_name)
    _check_super_cell_size(self, dim_name)


def _reject_unsupported_cartesian_grid_features(self):
    util.unsupported("moving window", self.moving_window_velocity)
    util.unsupported("refined regions", self.refined_regions, [])
    util.unsupported("lower bound (particles)", self.lower_bound_particles, self.lower_bound)
    util.unsupported("upper bound (particles)", self.upper_bound_particles, self.upper_bound)
    util.unsupported("pml cells", self.pml_cells)


def _check_lower_bound_is_zero(self):
    if any(bound != 0.0 for bound in self.lower_bound):
        raise ValueError(f"A lower bound different from 0 is not supported in PIConGPU. You gave {self.lower_bound}.")


def _check_boundary_conditions(self, dim_name):
    if self.lower_boundary_conditions != self.upper_boundary_conditions:
        raise ValueError(
            "upper and lower boundary conditions must be equal (can only be chosen by axis, not by direction)"
        )
    for i, name in enumerate(dim_name):
        if self.lower_boundary_conditions[i] not in PICONGPU_BOUNDARY_CONDITION_BY_PICMI_ID:
            raise ValueError(f"{name}: boundary condition not supported")


def _check_grid_distribution(self, dim_name):
    if self.picongpu_grid_dist is None:
        return
    for i, name in enumerate(dim_name):
        if not all(n >= 1 for n in self.picongpu_grid_dist[i]):
            raise ValueError("All values in grid distribution must be greater than 0.")
        if sum(self.picongpu_grid_dist[i]) != self.number_of_cells[i]:
            raise ValueError(f"sum of grid distribution in {name} dimension must match number of cells")
        if len(self.picongpu_grid_dist[i]) != self.picongpu_n_gpus[i]:
            raise ValueError(f"number of grid distributions in {name} dimension must match number of gpus")


def _check_super_cell_size(self, dim_name):
    for i, name in enumerate(dim_name):
        if self.picongpu_super_cell_size[i] < 1:
            raise ValueError("super cell size must be a positive integer")

    if self.guard_cells is not None:
        for i, name in enumerate(dim_name):
            guard_cells = self.guard_cells[i]
            super_cell = self.picongpu_super_cell_size[i]
            if guard_cells < 0:
                raise ValueError(
                    f"guard cells in {name} dimension must be a non-negative integer. You gave {guard_cells}."
                )
            if guard_cells % super_cell != 0:
                raise ValueError(
                    f"guard cells in {name} dimension must be an exact multiple of the super cell size "
                    f"({super_cell} in {name}), but you gave {guard_cells}."
                )
    cells = list(self.number_of_cells)
    for dim, name in enumerate(dim_name):
        if self.picongpu_grid_dist is None:
            if ((cells[dim] // self.picongpu_n_gpus[dim]) // self.picongpu_super_cell_size[dim]) * self.picongpu_n_gpus[
                dim
            ] * self.picongpu_super_cell_size[dim] != cells[dim]:
                raise ValueError(
                    "GPU- and/or super-cell-distribution in {} dimension does not match grid size".format(name)
                )
        else:
            # any returns true if there is at least one non zero (True) element
            if any([x % self.picongpu_super_cell_size[dim] for x in self.picongpu_grid_dist[dim]]):
                raise ValueError(f"grid distribution in {name} dimension must be multiple of super cell size")


@converts_to(
    grid.Grid3D,
    preamble=lambda self: _check_cartesian_grid(self, ["x", "y", "z"]),
    conversions={
        "boundary_condition": lambda self: tuple(
            PICONGPU_BOUNDARY_CONDITION_BY_PICMI_ID[x] for x in self.lower_boundary_conditions
        ),
        "cell_cnt": "number_of_cells",
        "guard_size": lambda self: (
            None
            if self.guard_cells is None
            else tuple(c // s for c, s in zip(self.guard_cells, self.picongpu_super_cell_size))
        ),
    },
    remove_prefix="picongpu_",
)
class Cartesian3DGrid(picmistandard.PICMI_Cartesian3DGrid):
    # number of GPUs to distribute the grid over; whatever form is given, it
    # is normalized to a 3-tuple (see _normalise_n_gpus): a bare int N and [N]
    # both mean "parallelize over N GPUs in y", i.e. (1, N, 1)
    picongpu_n_gpus: Annotated[
        int | Sequence[int] | None,
        BeforeValidator(_reject_bool_n_gpus),
        AfterValidator(lambda x: _normalise_n_gpus(x, 3)),
    ] = Field(default=(1, 1, 1))
    picongpu_grid_dist: None | list[list[int]] = Field(default=None)
    picongpu_super_cell_size: tuple[int, int, int] = Field(default=(8, 8, 4))

    @computed_field
    def picongpu_cell_size(self) -> tuple[int, int, int]:
        return (
            (self.upper_bound[0] - self.lower_bound[0]) / self.number_of_cells[0],
            (self.upper_bound[1] - self.lower_bound[1]) / self.number_of_cells[1],
            (self.upper_bound[2] - self.lower_bound[2]) / self.number_of_cells[2],
        )

    @model_validator(mode="after")
    def _validate(self):
        # A grid must be non-degenerate: every dimension needs at least one cell
        # and a strictly positive extent, otherwise the cell size below would be
        # undefined (ZeroDivisionError) or render an empty C++ grid.
        for dim, name in enumerate(["x", "y", "z"]):
            if self.number_of_cells[dim] < 1:
                raise ValueError(
                    f"number_of_cells[{dim}] ({name} dimension) must be a positive integer. "
                    f"You gave {self.number_of_cells[dim]}."
                )
            if self.upper_bound[dim] <= self.lower_bound[dim]:
                raise ValueError(
                    f"upper_bound in {name} dimension must be greater than lower_bound "
                    f"(got lower={self.lower_bound[dim]}, upper={self.upper_bound[dim]})."
                )
        return self

    @model_validator(mode="after")
    def _check_particle_boundary_conditions(self):
        # The standard's ``_resolve_grid`` (an after-validator of a base class)
        # fills in the derived fields while validating this model; with
        # ``validate_assignment`` enabled each such assignment re-triggers the
        # after-validators, so this runs on every intermediate state. The four
        # particle-derived fields below are the *last* ones ``_resolve_grid``
        # resolves, and in the fully-resolved model they are always non-None
        # (each inherits the field bound / condition when unset). Gating on them
        # means we validate exactly once, on the final state.
        if (
            self.lower_bound_particles is None
            or self.upper_bound_particles is None
            or self.lower_boundary_conditions_particles is None
            or self.upper_boundary_conditions_particles is None
        ):
            return self
        # Unset particle BCs are inherited from the field BCs by the standard's
        # ``_resolve_grid``; here we validate what was actually set (inherited or
        # explicit) and keep it per-axis, mirroring the field-boundary rule that
        # the lower and upper conditions must agree (PIConGPU chooses by axis,
        # not by direction).
        for dim, name in enumerate(["x", "y", "z"]):
            lower = self.lower_boundary_conditions_particles[dim]
            upper = self.upper_boundary_conditions_particles[dim]
            if lower != upper:
                raise ValueError(
                    f"{name}: lower and upper particle boundary conditions must be equal "
                    f"(can only be chosen by axis, not by direction). You gave {lower=}, {upper=}."
                )
            if lower not in PICONGPU_PARTICLE_BOUNDARY_CONDITION_BY_PICMI_ID:
                raise ValueError(f"{name}: particle boundary condition not supported. You gave {lower!r}.")
        return self

    def check(self):
        _check_cartesian_grid(self, ["x", "y", "z"])
        self._check_particle_boundary_conditions()

    @computed_field
    @property
    def picongpu_particle_boundary_conditions(self) -> tuple[str, str, str]:
        """Resolved per-axis particle boundary conditions (lower==upper, validated).

        These are the *grid defaults* for particle boundaries: when a species does not
        set its own ``picongpu_particle_boundary``, it inherits this grid's setting per
        axis. Values are the PICMI-standard names
        (``periodic``/``absorbing``/``reflect``/``thermal``); see
        :data:`PICONGPU_PARTICLE_BOUNDARY_CONDITION_BY_PICMI_ID` for the mapping to the
        PIConGPU ``--<species>_boundary`` tokens.
        """
        return tuple(self.lower_boundary_conditions_particles)

    def to_2d(self) -> "Cartesian2DGrid":
        """Reduce this 3D grid to a 2D (2D3V) grid, dropping the z (third) component.

        Every vector field is mapped from a 3-tuple to a 2-tuple by keeping the
        (x, y) components. The z cell length is preserved as the 2D slab
        thickness via ``picongpu_cell_depth_si``. If the 3D super cell is the
        default ``(8, 8, 4)`` it maps to the 2D default ``(16, 16)``; an
        explicitly-set 3D super cell keeps its (x, y) components (detected via
        ``model_fields_set``, not by value, so an explicit ``(8, 8, 4)`` is
        preserved as ``(8, 8)``). A fresh ``Cartesian2DGrid`` is returned and the
        source grid is not modified; the result is then validated with the 2D
        ``check()`` so a 3D grid whose reduction does not satisfy the 2D
        constraints raises at the call site rather than returning an invalid grid.
        """
        number_of_cells = self.number_of_cells[:2]
        lower_bound = self.lower_bound[:2]
        upper_bound = self.upper_bound[:2]
        lower_boundary_conditions = self.lower_boundary_conditions[:2]
        upper_boundary_conditions = self.upper_boundary_conditions[:2]

        # The 3D default super cell maps to the 2D default; an explicitly-set
        # super cell (including a deliberate ``(8, 8, 4)``) keeps its (x, y).
        # ``model_fields_set`` tells explicit from default; the value cannot.
        if "picongpu_super_cell_size" in self.model_fields_set:
            super_cell_size = self.picongpu_super_cell_size[:2]
        else:
            super_cell_size = (16, 16)

        kwargs = dict(
            number_of_cells=number_of_cells,
            lower_bound=lower_bound,
            upper_bound=upper_bound,
            lower_boundary_conditions=lower_boundary_conditions,
            upper_boundary_conditions=upper_boundary_conditions,
            picongpu_super_cell_size=super_cell_size,
            picongpu_cell_depth_si=self.picongpu_cell_size[2],
        )
        if self.guard_cells is not None:
            kwargs["guard_cells"] = self.guard_cells[:2]
        if self.picongpu_n_gpus != (1, 1, 1):
            kwargs["picongpu_n_gpus"] = self.picongpu_n_gpus[:2]
        if self.picongpu_grid_dist is not None:
            kwargs["picongpu_grid_dist"] = self.picongpu_grid_dist[:2]
        grid_2d = Cartesian2DGrid(**kwargs)
        grid_2d.check()
        return grid_2d

    def get_particle_boundary(
        self,
        name: str,
        picongpu_particle_boundary: "ParticleBoundary | None" = None,
    ) -> SpeciesParticleBoundary:
        """Resolve this grid's per-axis particle BC with an optional species override.

        The grid particle-BC is the **default**; the species'
        ``picongpu_particle_boundary`` (if given) **overrides** the grid's per-axis
        value. Returns a resolved :class:`pypicongpu...SpeciesParticleBoundary` that
        maps to the per-species command-line options (``--<species>_boundary`` and
        friends).

        The C++ core's compatibility constraints (reflecting/thermal only
        on absorbing-field axes; periodic only on periodic-field axes; periodic
        requires a 0 offset) are enforced here, at translation time.
        """
        return particle_boundary.resolve_species_particle_boundary(
            name=name,
            field_boundary_conditions=self.lower_boundary_conditions,
            grid_particle_boundary_conditions=self.picongpu_particle_boundary_conditions,
            override=picongpu_particle_boundary,
        )


@converts_to(
    grid.Grid2D,
    preamble=lambda self: _check_cartesian_grid(self, ["x", "y"]),
    conversions={
        "boundary_condition": lambda self: tuple(
            PICONGPU_BOUNDARY_CONDITION_BY_PICMI_ID[x] for x in self.lower_boundary_conditions
        ),
        "cell_cnt": "number_of_cells",
        # In 2D3V the Z cell length (CELL_DEPTH_SI) is still used to normalize
        # densities; we take the x cell size as the default wire-particle length
        # unless the user explicitly overrides it via picongpu_cell_depth_si.
        "cell_depth_si": lambda self: (
            self.picongpu_cell_depth_si
            if self.picongpu_cell_depth_si is not None
            else (self.upper_bound[0] - self.lower_bound[0]) / self.number_of_cells[0]
        ),
        "guard_size": lambda self: (
            None
            if self.guard_cells is None
            else tuple(c // s for c, s in zip(self.guard_cells, self.picongpu_super_cell_size))
        ),
    },
    remove_prefix="picongpu_",
)
class Cartesian2DGrid(picmistandard.PICMI_Cartesian2DGrid):
    # number of GPUs to distribute the grid over; whatever form is given, it
    # is normalized to a 2-tuple (see _normalise_n_gpus): a bare int N and [N]
    # both mean "parallelize over N GPUs in y", i.e. (1, N)
    picongpu_n_gpus: Annotated[
        int | Sequence[int] | None,
        BeforeValidator(_reject_bool_n_gpus),
        AfterValidator(lambda x: _normalise_n_gpus(x, 2)),
    ] = Field(default=(1, 1))
    picongpu_grid_dist: None | list[list[int]] = Field(default=None)
    # PIConGPU's 2D setups (e.g. the FoilLCT example) use a <16, 16> super cell.
    picongpu_super_cell_size: tuple[int, int] = Field(default=(16, 16))
    # In 2D3V the Z cell length (CELL_DEPTH_SI) is the wire-particle integration
    # length used to normalize densities. When left as None, the conversion falls
    # back to the x cell size (dx); set it to override the slab thickness.
    picongpu_cell_depth_si: Annotated[
        float | None,
        AfterValidator(
            lambda x: x if x is None or x > 0 else (_ for _ in ()).throw(ValueError("cell depth must be > 0"))
        ),
    ] = Field(default=None)

    @computed_field
    def picongpu_cell_size(self) -> tuple[int, int]:
        return (
            (self.upper_bound[0] - self.lower_bound[0]) / self.number_of_cells[0],
            (self.upper_bound[1] - self.lower_bound[1]) / self.number_of_cells[1],
        )

    @model_validator(mode="after")
    def _validate(self):
        # A grid must be non-degenerate: every dimension needs at least one cell
        # and a strictly positive extent, otherwise the cell size below would be
        # undefined (ZeroDivisionError) or render an empty C++ grid.
        for dim, name in enumerate(["x", "y"]):
            if self.number_of_cells[dim] < 1:
                raise ValueError(
                    f"number_of_cells[{dim}] ({name} dimension) must be a positive integer. "
                    f"You gave {self.number_of_cells[dim]}."
                )
            if self.upper_bound[dim] <= self.lower_bound[dim]:
                raise ValueError(
                    f"upper_bound in {name} dimension must be greater than lower_bound "
                    f"(got lower={self.lower_bound[dim]}, upper={self.upper_bound[dim]})."
                )
        return self

    def check(self):
        _check_cartesian_grid(self, ["x", "y"])


AnyGrid = Cartesian3DGrid | Cartesian2DGrid
