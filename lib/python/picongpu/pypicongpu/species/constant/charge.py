"""
This file is part of PIConGPU.
Copyright 2021-2024 PIConGPU contributors
Authors: Hannes Troepgen, Brian Edward Marre
License: GPLv3+
"""

from .constant import Constant


class Charge(Constant):
    """
    charge of a physical particle

    C++ counterpart: ChargeRatio_<typename> in
    include/picongpu/param/speciesDefinition.param,
    rendered as `charge_si / sim.si.getBaseCharge()` (base charge = elementary charge).

    Units policy: SI (C). The sign is free: electrons carry a negative
    charge, ions a positive one, so no sign constraint is applied.
    """

    charge_si: float
    """charge of an individual particle, [C]; can be negative (e.g. electrons),
    zero for neutral species is accepted by the rendering but rarely used.
    C++ name: ChargeRatio_<typename> (speciesDefinition.param)."""
