"""
This file is part of PIConGPU.
Copyright 2021-2026 PIConGPU contributors
Authors: Hannes Troepgen, Brian Edward Marre, Julian Lenz
License: GPLv3+
"""

from typing import Annotated

from pydantic import Field, computed_field

from .constant import Constant
from .speciesconstants import SPECIES_CONSTANTS


class Mass(Constant):
    """
    mass of a physical particle

    C++ counterpart: MassRatio_<typename> in
    include/picongpu/param/speciesDefinition.param, a ratio relative to the
    base mass SI::BASE_MASS_SI (speciesConstants.param, fixed to the electron
    mass).

    The absolute SI mass is stored (task-06 unit policy) and the ratio is
    derived from it here at the pypicongpu level (instead of in the
    template), mirroring the C++ structure where speciesDefinition.param
    only knows the ratio relative to the base constants.

    Units policy: mass_si in SI (kg); mass_ratio dimensionless.
    """

    mass_si: Annotated[float, Field(ge=0.0)]
    """mass of an individual particle, [kg]; must be >= 0. Zero is only valid for
    massless particles (e.g. photons using the Photon pusher); a negative mass
    is unphysical.
    C++ reference: SI::BASE_MASS_SI (speciesConstants.param)."""

    @computed_field
    def mass_ratio(self) -> float:
        """mass ratio relative to the base mass (electron mass),
        [dimensionless]; rendered into speciesDefinition.param.
        C++ name: MassRatio_<typename> (speciesDefinition.param)."""
        return self.mass_si / SPECIES_CONSTANTS.base_mass_si
