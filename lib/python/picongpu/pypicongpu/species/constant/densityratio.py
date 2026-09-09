"""
This file is part of PIConGPU.
Copyright 2021-2024 PIConGPU contributors
Authors: Hannes Troepgen, Brian Edward Marre
License: GPLv3+
"""

from typing import Annotated

from pydantic import Field

from picongpu.pypicongpu.species.constant import Constant


class DensityRatio(Constant):
    """
    factor for weighting when using profiles/deriving

    C++ counterpart: DensityRatio_<typename> in
    include/picongpu/param/speciesDefinition.param.

    Units policy: dimensionless factor relative to the simulation
    base density.
    """

    ratio: Annotated[float, Field(gt=0.0)]
    """factor for weighting calculation, [dimensionless]; must be > 0.
    C++ name: DensityRatio_<typename> (speciesDefinition.param)."""
