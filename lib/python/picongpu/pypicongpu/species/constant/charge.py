"""
This file is part of PIConGPU.
Copyright 2021-2026 PIConGPU contributors
Authors: Hannes Troepgen, Brian Edward Marre, Julian Lenz
License: GPLv3+
"""

from pydantic import computed_field

from .constant import Constant
from .speciesconstants import SPECIES_CONSTANTS


class Charge(Constant):
    """
    charge of a physical particle

    C++ counterpart: ChargeRatio_<typename> in
    include/picongpu/param/speciesDefinition.param, a ratio relative to the
    base charge SI::BASE_CHARGE_SI (speciesConstants.param, fixed to the
    negative electron charge).

    The absolute SI charge is stored (task-06 unit policy) and the ratio is
    derived from it here at the pypicongpu level (instead of in the
    template), mirroring the C++ structure where speciesDefinition.param
    only knows the ratio relative to the base constants.

    Units policy: charge_si in SI (C); charge_ratio dimensionless. The sign
    is free: electrons carry a negative charge, ions a positive one, so no
    sign constraint is applied (the ratio of an electron is +1, of a proton
    -1, as in the C++ default speciesDefinition.param).
    """

    charge_si: float
    """charge of an individual particle, [C]; can be negative (e.g. electrons),
    zero for neutral species is accepted by the rendering but rarely used.
    C++ reference: SI::BASE_CHARGE_SI (speciesConstants.param)."""

    @computed_field
    def charge_ratio(self) -> float:
        """charge ratio relative to the base charge (negative electron charge),
        [dimensionless]; rendered into speciesDefinition.param.
        C++ name: ChargeRatio_<typename> (speciesDefinition.param)."""
        return self.charge_si / SPECIES_CONSTANTS.base_charge_si
