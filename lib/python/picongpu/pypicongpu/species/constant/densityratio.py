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
    per-species density ratio

    C++ counterpart: DensityRatio_<typename> in
    include/picongpu/param/speciesDefinition.param, a runtime-tunable
    value_identifier passed to the species frame as the densityRatio<> flag
    and read back via traits::GetDensityRatio.

    The density profile is normalized to SI::BASE_DENSITY_SI (simulation.param);
    this ratio is the factor the species' profile-derived density is scaled by
    (ParticlesInit.kernel), and species *derived* from the created one inside a
    CreateDensity are scaled by the ratio of their density ratios
    (manipulators::binary::DensityWeighting).

    A species without this constant gets no densityRatio<> flag, and the C++
    trait then falls back to the default of 1.0; omitting it here is thus
    equivalent to ratio == 1.0.

    Units policy: dimensionless factor.
    """

    ratio: Annotated[float, Field(gt=0.0)]
    """factor for weighting calculation, [dimensionless]; must be > 0.
    C++ name: DensityRatio_<typename> (speciesDefinition.param)."""
