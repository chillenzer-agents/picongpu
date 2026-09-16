"""
This file is part of PIConGPU.
Copyright 2024-2024 PIConGPU contributors
Authors: Brian Edward Marre
License: GPLv3+
"""

import sympy

from picongpu.picmi.copy_attributes import converts_to
from picongpu.pypicongpu import species
from picongpu.pypicongpu.species.operation.densityprofile.gaussian import Gaussian
from ...pypicongpu import util

from .AnalyticDistribution import AnalyticDistribution
from .Distribution import Distribution

import numpy as np


def _gaussian_density_function(params, cell_size, x, y, z):
    """
    The native Gaussian profile, written as a sympy ``Piecewise`` over the cell-centre
    position (which is what the pypicongpu free-formula functor evaluates it at).

    This reproduces the C++ ``GaussianImpl`` exactly, including the cell-centre
    correction: the front/plateau/rear ramps are defined over the cell *origin*, so the
    cell-centre input is shifted by ``-0.5 * cell_size_y``. The vacuum boundary is
    ``int(vacuum_front / cell_size_y)`` cells in the native code (an integer cell-index
    comparison), which is reproduced here by ``-0.5 * cell_size_y`` in the shifted
    boundary so that a cell-centre is classified identically to the integer cell index.
    """
    if cell_size is None:
        raise NotImplementedError(
            "Evaluating the bounded Gaussian profile requires the cell size. It is set "
            "automatically when the simulation writes the input files, exactly like the "
            "unbounded Gaussian."
        )
    cell_size_y = cell_size[1]
    # The definition of this density uses the origin of the cell while the call operator
    # (and the free-formula C++ functor) use the center.
    y = y + -0.5 * cell_size_y
    # The last term undoes the shift to the cell origin.
    vacuum_y = int(params["vacuum_front"] / cell_size_y) * cell_size_y - 0.5 * cell_size_y

    exponent = sympy.Piecewise(
        (sympy.Abs((y - params["center_front"]) / params["sigma_front"]), y < params["center_front"]),
        (sympy.Abs((y - params["center_rear"]) / params["sigma_rear"]), y >= params["center_rear"]),
        (0.0, True),
    )
    return sympy.Piecewise(
        (0.0, y < vacuum_y), (params["density"] * sympy.exp(params["factor"] * exponent ** params["power"]), True)
    )


class BoundedGaussianDistribution(AnalyticDistribution):
    """
    A Gaussian profile rendered as an analytic (free-formula) density.

    Used whenever a :class:`GaussianDistribution` is given sub-volume bounds
    (``lower_bound`` / ``upper_bound``): the native pypicongpu ``Gaussian`` model has no
    bound fields and the C++ ``GaussianImpl`` does not implement sub-volume boxes, so the
    bounded profile is reconstructed as an :class:`AnalyticDistribution`.

    The profile reproduces the native y-only Gaussian (front/plateau/rear ramps + vacuum
    front) exactly, including the cell-centre correction, and stores the full 3-vector
    bounds. Note that the PIConGPU C++ core does not (yet) apply the sub-volume bounds when
    sampling particles; this form documents and pins the working workaround.
    """

    cell_size: tuple[float, float, float] | None = None
    rms_velocity: tuple[float, float, float] = (0.0, 0.0, 0.0)

    def __init__(
        self,
        density,
        center_front,
        center_rear,
        sigma_front,
        sigma_rear,
        power,
        factor,
        vacuum_front,
        lower_bound,
        upper_bound,
        rms_velocity=(0.0, 0.0, 0.0),
        directed_velocity=(0.0, 0.0, 0.0),
        fill_in=True,
        **kwargs,
    ):
        super().__init__(
            density_function=lambda x, y, z: _gaussian_density_function(self._params, self.cell_size, x, y, z),
            lower_bound=list(lower_bound),
            upper_bound=list(upper_bound),
            rms_velocity=tuple(rms_velocity),
            directed_velocity=directed_velocity,
            fill_in=fill_in,
            **kwargs,
        )
        self._params = dict(
            density=density,
            center_front=center_front,
            center_rear=center_rear,
            sigma_front=sigma_front,
            sigma_rear=sigma_rear,
            power=power,
            factor=factor,
            vacuum_front=vacuum_front,
        )
        # Mirror the gaussian-specific validation of the unbounded Gaussian.
        util.unsupported("fill in not active", fill_in, True)
        if center_rear < center_front:
            raise ValueError("center_front must be <= center_rear")
        if density <= 0.0:
            raise ValueError("density must be > 0")

    def get_as_pypicongpu(self, grid):
        self.cell_size = tuple(grid.picongpu_cell_size)
        return species.operation.densityprofile.FreeFormula(density_expression=self._density_expression())


_DEFAULT_BOUNDS = (None, None, None)


def _bounds_are_set(bounds):
    return any(value is not None for value in bounds)


@converts_to(
    Gaussian,
    conversions={"vacuum_cells_front": lambda self, _: int(self.vacuum_front / self.cell_size[1])},
    preamble=lambda self, grid: setattr(self, "cell_size", grid.picongpu_cell_size) or self.check(),
    ignore=["check"],
)
class GaussianDistribution(Distribution):
    """
    Describes a density distribution of particles with gaussian up- and down-ramps with a constant density region in
    between

    Will create the following profile:
    - for y < center_front:                density * exp(factor * abs(y - center_front/sigma_front)**power)
    - for center_front <= y <=center_rear: density
    - for y > center_rear:                 density * exp(factor * abs(y - center_rear/sigma_rear)**power)

    with y being the position in the simulation box

    Sub-volume bounds
    -----------------
    The native pypicongpu ``Gaussian`` model has no bound fields, and the C++
    ``GaussianImpl`` does not implement sub-volume boxes. When ``lower_bound`` /
    ``upper_bound`` are given, this class therefore instantiates a
    :class:`BoundedGaussianDistribution` (an :class:`AnalyticDistribution`) instead, which
    reproduces the native profile exactly and stores the full 3-vector bounds.
    """

    density: float
    """particle number density, [m^-3]"""

    center_front: float
    """center of gaussian ramp at the front, [m]"""
    center_rear: float
    """center of the gaussian ramp at the rear, [m]"""

    sigma_front: float
    """sigma of the gaussian ramp at the front, [m]"""
    sigma_rear: float
    """sigma of the gaussian ramp at the rear, [m]"""

    power: float
    """power used in exponential function, 2 will yield a gaussian, 4+ a super-gaussian, unitless"""
    factor: float
    """sign and scaling factor, must be < 0, unitless"""

    vacuum_front: float
    """size of the vacuum in front of density, gets rounded down to full cells, [m]"""

    lower_bound: tuple[float, float, float] | tuple[None, None, None] = (
        None,
        None,
        None,
    )
    upper_bound: tuple[float, float, float] | tuple[None, None, None] = (
        None,
        None,
        None,
    )

    cell_size: tuple[float, float, float] | None = None

    # @details pydantic provides an automatically generated __init__/constructor method which allows initialization off
    #   all attributes as keyword arguments

    def __new__(cls, *args, **kwargs):
        lower_bound = kwargs.get("lower_bound", _DEFAULT_BOUNDS)
        upper_bound = kwargs.get("upper_bound", _DEFAULT_BOUNDS)
        if _bounds_are_set(lower_bound) or _bounds_are_set(upper_bound):
            # Sub-volume bounds requested: the native pypicongpu Gaussian has no bound
            # fields, so return the analytic (free-formula) form instead. Returning an
            # object that is not a GaussianDistribution also skips the Gaussian
            # __init__/validation, so the bounded profile carries its own semantics.
            return BoundedGaussianDistribution(
                density=kwargs["density"],
                center_front=kwargs["center_front"],
                center_rear=kwargs["center_rear"],
                sigma_front=kwargs["sigma_front"],
                sigma_rear=kwargs["sigma_rear"],
                power=kwargs["power"],
                factor=kwargs["factor"],
                vacuum_front=kwargs["vacuum_front"],
                lower_bound=lower_bound,
                upper_bound=upper_bound,
                rms_velocity=kwargs.get("rms_velocity", (0.0, 0.0, 0.0)),
                directed_velocity=kwargs.get("directed_velocity", (0.0, 0.0, 0.0)),
                fill_in=kwargs.get("fill_in", True),
            )
        return object.__new__(cls)

    def check(self):
        util.unsupported("fill in not active", self.fill_in, True)
        if self.center_rear < self.center_front:
            raise ValueError("center_front must be <= center_rear")
        if self.density <= 0.0:
            raise ValueError("density must be > 0")

    def __call__(self, x, y, z):
        if self.cell_size is None:
            message = (
                "Due to inconsistencies in the backend, evaluation of this function requires information about the cell_size."
                " You can either set it manually "
                " or you can perform anything that includes writing the input files on your simulation object."
                " This is a temporary workaround and will be fixed in the future."
            )
            raise NotImplementedError(message)

        # The definition of this density uses the origin of the cell
        # while the call operator uses the center.
        x += -0.5 * self.cell_size[0]
        y += -0.5 * self.cell_size[1]
        z += -0.5 * self.cell_size[2]

        # The last term undoes the shift to the cell origin.
        vacuum_y = int(self.vacuum_front / self.cell_size[1]) * self.cell_size[1] - 0.5 * self.cell_size[1]

        # We do this to get the correct shape after broadcasting:
        exponent = 0 * (x + y + z)
        exponent[y < self.center_front] = np.abs((y - self.center_front) / self.sigma_front)[y < self.center_front]
        exponent[y >= self.center_rear] = np.abs((y - self.center_rear) / self.sigma_rear)[y >= self.center_rear]

        result = np.exp(self.factor * exponent**self.power)
        result[y < vacuum_y] = 0.0
        return self.density * result
