"""
This file is part of PIConGPU.
Copyright 2023-2024 PIConGPU contributors
Authors: Kristin Tippey, Brian Edward Marre
License: GPLv3+
"""

from functools import partial
from math import sqrt
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, Field, PlainSerializer, model_validator

from ....validation import component_vector, radius_larger_than
from ....vector import serialise_vec

from .plasmaramp import AllPlasmaRamps, None_


class Cylinder(BaseModel):
    """
    Describes a cylindrical density distribution of particles with gaussian up-ramp
    with a constant density region in between. It can have an arbitrary orientation
    and position in space.

    Will create the following profile:
      n = density if r < reduced_radius
      n is 0 or follows the exponential ramp if r > reduced_radius
      n is 0 if r > reduced_radius + prePlasmaCutoff
      the reduced_radius is equal = @f[\\sqrt{R^2 -L^2} -L @f]
      with R - cylinder_radius and L - prePlasmaLength (scale length of the ramp)
      the reduced radius ensures mass conservation
    """

    type_cylinder: Literal[True] = True

    density_si: float = Field(gt=0.0)
    """particle number density at at the foil plateau (m^-3)"""

    center_position_si: Annotated[
        tuple[float, float, float],
        BeforeValidator(partial(component_vector, field="center_position_si")),
        PlainSerializer(serialise_vec),
    ]
    """center of the cylinder [x, y, z], [m]"""

    radius_si: float
    """cylinder radius, [m]"""

    cylinder_axis: Annotated[
        tuple[float, float, float],
        BeforeValidator(partial(component_vector, field="cylinder_axis")),
        PlainSerializer(serialise_vec),
    ]
    """cylinder axis [x, y, z], [unitless]"""

    # This still relies on some magic to insert the typeID.
    # We'll handle it another time:
    pre_plasma_ramp: AllPlasmaRamps = None_()
    """pre plasma ramp"""

    @model_validator(mode="after")
    def check(self):
        min_radius = sqrt(2.0) * self.pre_plasma_ramp.PlasmaLength if type(self.pre_plasma_ramp) is not None_ else 0.0
        radius_larger_than(
            self.radius_si,
            min_radius,
            field="radius_si",
        )
        return self
