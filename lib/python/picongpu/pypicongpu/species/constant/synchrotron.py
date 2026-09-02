"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

from typing import Annotated, Any

from pydantic import BaseModel, Field, model_validator
from picongpu.pypicongpu.species.constant.constant import Constant


class FirstSynchrotronFunctionParams(BaseModel):
    """
    Parameters for computing the first synchrotron function.

    Corresponds to FirstSynchrotronFunctionParams struct in C++
    (include/picongpu/param/synchrotron.param).

    Units policy: all values dimensionless (log2 cutoffs, counts).
    """

    log_end: Annotated[float, Field(gt=0.0)] = 7.0
    """
    log2 of the argument cutoff for the 2nd kind cyclic Bessel function
    (default log2(100.0)), [dimensionless]; must be > 0.
    C++ name: logEnd.
    """

    num_sample_points: Annotated[int, Field(ge=1)] = 8096
    """
    Number of sample points to use in integration in firstSynchrotronFunction,
    [dimensionless]; must be >= 1.
    C++ name: numberSamplePoints.
    """


class InterpolationParams(BaseModel):
    """
    Parameters for precomputation of interpolation table.

    Corresponds to InterpolationParams struct in C++
    (include/picongpu/param/synchrotron.param).

    Units policy: all values dimensionless (log2 exponents, counts).
    """

    number_table_entries: Annotated[int, Field(ge=1)] = 512
    """
    Number of synchrotron function values to precompute and store in table,
    [dimensionless]; must be >= 1.
    C++ name: numberTableEntries.
    """

    min_Zq_exponent: float = -50.0
    """
    Lower bound of the interpolated Zq range in log2: -50 means minimum Zq
    that is still not 0 is 2^-50 ~ 10^-15, [dimensionless].
    C++ name: minZqExponent.
    """

    max_Zq_exponent: Annotated[float, Field(le=10.0)] = 10.0
    """
    Upper bound of the interpolated Zq range in log2: 10 means maximum Zq
    that is still not 0 is 2^10 ~ 10^+3, [dimensionless]; must be <= 10
    (larger values can result in a runtime error in precomputing the
    cyclic Bessel function).
    C++ name: maxZqExponent.
    """

    @model_validator(mode="after")
    def check(self):
        if self.min_Zq_exponent >= self.max_Zq_exponent:
            raise ValueError(
                "min_Zq_exponent must be smaller than max_Zq_exponent. "
                f"You gave: {self.min_Zq_exponent=} and {self.max_Zq_exponent=}."
            )
        return self


class SynchrotronParams(BaseModel):
    """
    Synchrotron radiation.

    C++ counterpart: include/picongpu/param/synchrotron.param.

    Units policy: min_energy in joule, everything else dimensionless.
    """

    electron_recoil: bool = True
    """
    Turn off or turn on the electron recoil from electrons generated,
    [dimensionless flag].
    C++ name: ElectronRecoil.
    """

    min_energy: Annotated[float | None, Field(gt=0.0)] = None
    """
    Energy high-pass filter: accept only photons with energy higher than this
    value, [J]; must be > 0 when set (default: hbar/dt is used).
    C++ name: minEnergy.
    """

    first_synchrotron_function_params: FirstSynchrotronFunctionParams = FirstSynchrotronFunctionParams()
    """
    Parameters for computing the first synchrotron function.
    """

    interpolation_params: InterpolationParams = InterpolationParams()
    """
    Parameters for precomputation of interpolation table.
    """

    supress_requirement_warning: bool = False
    """
    If true, the warning for requirement 1 and 2 is suppressed,
    [dimensionless flag].

    This may speed the simulation a little bit because there is no call to global memory.

    This warning means that the probability of generating a photon is high for given dt
    (higher than 10%) - this means we generate photons possibly every timestep
    (numerical artefacts) and the radiation is underestimated if probability is greater than 1.
    The timestep should be reduced.
    C++ name: supressRequirementWarning.
    """


class SynchrotronConstant(Constant):
    """
    constant marking a species as the photon species of the synchrotron plugin

    C++ counterpart: the `synchrotron<PhotonSpecies>` particle flag in
    include/picongpu/param/speciesDefinition.param.
    """

    photon_species: Any
    """species (or species name) used as the photon species for synchrotron radiation."""
