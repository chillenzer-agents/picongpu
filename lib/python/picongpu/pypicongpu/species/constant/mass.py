"""
This file is part of PIConGPU.
Copyright 2021-2024 PIConGPU contributors
Authors: Hannes Troepgen, Brian Edward Marre
License: GPLv3+
"""

from typing import Annotated

from pydantic import Field

from picongpu.pypicongpu.units import SI

from .constant import Constant


class Mass(Constant):
    """
    mass of a physical particle

    C++ counterpart: MassRatio_<typename> in
    include/picongpu/param/speciesDefinition.param,
    rendered as `mass_si / sim.si.getBaseMass()` (base mass = proton mass).

    Units policy: SI (kg).
    """

    mass_si: Annotated[float, Field(ge=0.0), SI("kg")]
    """mass of an individual particle, [kg]; must be >= 0. Zero is only valid for
    massless particles (e.g. photons using the Photon pusher); a negative mass
    is unphysical.
    C++ name: MassRatio_<typename> (speciesDefinition.param)."""
