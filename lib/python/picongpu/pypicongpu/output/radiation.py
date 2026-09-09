"""
This file is part of PIConGPU.
Copyright 2025 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

from enum import Enum
from operator import attrgetter, itemgetter
from typing import Annotated, Callable, Literal

from pydantic import BaseModel, Field, computed_field, field_validator, model_validator
from sympy import Expr, Symbol
from sympy.vector import CoordSys3D, Vector

from picongpu.pypicongpu.output.timestepspec import TimeStepSpec
from picongpu.pypicongpu.particle_functor.filtered_species import FilteredSpecies
from picongpu.pypicongpu.rendering.pmaccprinter import PMAccPrinter
from picongpu.pypicongpu.species import Species


class LinearFrequencies(BaseModel):
    """
    linear frequency scale for the radiation calculation

    C++ counterpart: the frequency scale parameters of the radiation plugin
    (type "linear": N_omega, omega_min, omega_max).

    Units policy: angular frequencies in [1/s].
    """

    N_omega: Annotated[int, Field(ge=1)] = 2048
    """number of frequency points, [dimensionless]; must be >= 1"""

    omega_min: Annotated[float, Field(ge=0.0)] = 0.0
    """lowest angular frequency of the scale, [1/s]; must be >= 0 and < omega_max"""

    omega_max: Annotated[float, Field(gt=0.0)] = 1.06e16
    """highest angular frequency of the scale, [1/s]; must be > 0 and > omega_min"""

    type_linear_frequencies: Literal[True] = True
    """tag field identifying the linear frequency scale (discriminator)"""

    @model_validator(mode="after")
    def _check_omega_range(self):
        if self.omega_min >= self.omega_max:
            raise ValueError(
                f"omega_min must be smaller than omega_max. "
                f"You gave omega_min={self.omega_min}, omega_max={self.omega_max}."
            )
        return self


class LogFrequencies(BaseModel):
    """
    logarithmic frequency scale for the radiation calculation

    C++ counterpart: the frequency scale parameters of the radiation plugin
    (type "log": N_omega, omega_min, omega_max).

    Units policy: angular frequencies in [1/s].
    """

    N_omega: Annotated[int, Field(ge=1)] = 2048
    """number of frequency points, [dimensionless]; must be >= 1"""

    omega_min: Annotated[float, Field(gt=0.0)] = 1.0e14
    """lowest angular frequency of the scale, [1/s]; must be > 0 (logarithm is
    undefined for non-positive frequencies) and < omega_max"""

    omega_max: Annotated[float, Field(gt=0.0)] = 1.0e17
    """highest angular frequency of the scale, [1/s]; must be > 0 and > omega_min"""

    type_log_frequencies: Literal[True] = True
    """tag field identifying the logarithmic frequency scale (discriminator)"""

    @model_validator(mode="after")
    def _check_omega_range(self):
        if self.omega_min >= self.omega_max:
            raise ValueError(
                f"omega_min must be smaller than omega_max. "
                f"You gave omega_min={self.omega_min}, omega_max={self.omega_max}."
            )
        return self


class FrequenciesFromList(BaseModel):
    """
    frequency scale for the radiation calculation read from a file

    C++ counterpart: the frequency scale parameters of the radiation plugin
    (type "from list": N_omega, list_location).

    Units policy: frequencies in [1/s].
    """

    N_omega: Annotated[int, Field(ge=1)] = 2048
    """number of frequency points, [dimensionless]; must be >= 1"""

    list_location: Annotated[str, Field(min_length=1)]
    """path to a text file containing the frequencies, one per line, [1/s]; must not be empty"""

    type_frequencies_from_list: Literal[True] = True
    """tag field identifying the from-list frequency scale (discriminator)"""


FrequencyConfiguration = LinearFrequencies | LogFrequencies | FrequenciesFromList


class FormFactorConfiguration(Enum):
    """Form factor settings for radiation calculation."""

    CIC_3D = "CIC_3D"
    TSC_3D = "TSC_3D"
    PCS_3D = "PCS_3D"
    CIC_1Dy = "CIC_1Dy"
    Gauss_spherical = "Gauss_spherical"
    Gauss_cell = "Gauss_cell"
    incoherent = "incoherent"
    coherent = "coherent"


class WindowFunctionConfiguration(Enum):
    """Window function settings for radiation."""

    Triangle = "Triangle"
    Hamming = "Hamming"
    Triplett = "Triplett"
    Gauss = "Gauss"
    NONE = "None"


def _make_vector(coefficients, basis_vectors=CoordSys3D("e")):
    # In sympy, vectors are represented as linear combinations of basis vectors.
    # The last argument is important.
    # Otherwise Python tries to start from an integer (scalar) 0 which is not well-defined.
    return sum((coeff * vec for coeff, vec in zip(coefficients, basis_vectors)), Vector.zero)


class RadiationObserverConfiguration(BaseModel):
    """
    observer (virtual detector) configuration for the radiation plugin

    C++ counterpart: the observer direction mapping of the radiation plugin
    (N_observer and the direction expression per observer index).

    Units policy: dimensionless (indices and direction cosines).
    """

    N_observer: Annotated[int, Field(ge=1)] = 256
    """total number of observation directions, [dimensionless]; must be >= 1"""

    index_to_direction: Annotated[Callable[[Symbol], tuple[Expr, Expr, Expr]], Field(exclude=True)]
    """sympy mapping from the observer index to a (nonzero, normalisable) 3D
    direction vector; normalised to unit length during validation"""

    @field_validator("index_to_direction", mode="after")
    @classmethod
    def _validate_index_to_direction(cls, value):
        index = Symbol("index")
        vec = _make_vector(value(index))
        if vec.magnitude().equals(1):
            return value
        if vec.magnitude().equals(0):
            raise ValueError(f"The index_to_direction expression must be normalisable. You gave: {vec=} with norm 0.")
        return lambda arg: tuple(
            map(itemgetter(2), sorted(vec.normalize().subs(index, arg).components.items(), key=itemgetter(1)))
        )

    @computed_field
    def component_expressions(self) -> dict[str, str]:
        return {
            key: PMAccPrinter().doprint(value) for key, value in zip("xyz", self.index_to_direction(Symbol("index")))
        }


class RadiationConfiguration(BaseModel):
    """
    core radiation calculation parameters

    C++ counterpart: the core parameters of the radiation plugin
    (verbose level, frequency scale, Nyquist factor, form factor).

    Units policy: angular frequencies in [1/s] (via the frequency scale);
    all other quantities dimensionless.
    """

    verbose_level: Annotated[int, Field(ge=0)] = 3
    """verbose level (0=nothing, 1=physics, 2=sim_state, 4=memory, 8=critical),
    [dimensionless]; must be >= 0"""

    frequencies: FrequencyConfiguration = Field(default_factory=LinearFrequencies)
    """frequency scale configuration (linear, logarithmic, or from list)"""

    nyquist_factor: Annotated[float, Field(gt=0.0, lt=1.0)] = 0.5
    """Nyquist factor for the time integration, [dimensionless]; must satisfy 0 < factor < 1"""

    form_factor: FormFactorConfiguration = FormFactorConfiguration.Gauss_spherical
    """form factor type for the particle charge distribution"""


class RadiationPluginConfig(BaseModel):
    """
    complete radiation plugin configuration

    C++ counterpart: include/picongpu/plugins/radiation (the
    --radiation.* parameters in the generated N.cfg).

    Combines radiation settings, observer settings, and window function
    configuration into a single coherent model.

    Units policy: time steps and thresholds are dimensionless unless tagged.
    """

    radiation: RadiationConfiguration = Field(default_factory=RadiationConfiguration)
    """core radiation plugin configuration"""

    observer: RadiationObserverConfiguration
    """observer configuration for the virtual detectors"""

    window_function: WindowFunctionConfiguration = WindowFunctionConfiguration.NONE
    """window function to reduce ringing effects"""

    num_accumulation_steps: Annotated[int, Field(ge=0)] = 0
    """period, after which the calculated radiation data are dumped to the
    file system, [time-step number]; must be >= 0 (0 = never)"""

    last_radiation: bool = False
    """if set, the radiation spectra summed between the last and the current
    dump time step are stored"""

    folder_last_rad: str = "lastRad"
    """folder name for the summed spectra between the last and the current
    dump time step"""

    total_radiation: bool = False
    """if set, the spectra summed from simulation start till the current time
    step are stored"""

    folder_total_rad: str = "totalRad"
    """folder name for the total radiation spectra, integrated from the
    beginning of the simulation"""

    start: Annotated[int, Field(ge=0)] = 2
    """time step at which PIConGPU starts calculating the radiation,
    [time-step number]; must be >= 0 (default 2: enough particle history)"""

    end: Annotated[int, Field(ge=0)] = 0
    """time step at which the radiation calculation ends, [time-step number];
    must be >= 0 (0 = until the end of the simulation)"""

    rad_per_gpu: bool = False
    """if set, each GPU additionally stores its own spectra without summing
    over the entire simulation area"""

    folder_rad_per_gpu: str = "radPerGPU"
    """folder name for the GPU-specific spectra"""

    num_jobs: Annotated[int, Field(ge=1)] = 2
    """number of independent jobs used for the radiation calculation,
    [dimensionless]; must be >= 1"""

    open_pmd_suffix: str = "_%T_0_0_0.h5"
    """suffix for the openPMD filename extension and iteration expansion
    pattern"""

    open_pmd_checkpoint_extension: str = "h5"
    """filename extension for openPMD checkpoints"""

    open_pmd_config: str = "{}"
    """JSON/TOML configuration for initializing openPMD (empty = none)"""

    open_pmd_checkpoint_config: str = "{}"
    """JSON/TOML configuration for initializing openPMD checkpointing
    (empty = none)"""

    distributed_amplitude: bool = False
    """if set, output the distributed amplitudes per MPI rank in the
    openPMD output"""


class RadiationPlugin(BaseModel):
    """
    the radiation plugin (top level)

    C++ counterpart: the radiation plugin instance in
    include/picongpu/plugins (type tag + config + species + period).

    Units policy: see the sub-models.
    """

    type_radiation: Literal[True] = True
    """tag field identifying the radiation plugin (discriminator)"""

    config: RadiationPluginConfig
    """the complete radiation plugin configuration"""

    species: list[Species | FilteredSpecies]
    """the particle species (or filtered species) whose radiation is
    calculated"""

    period: TimeStepSpec
    """the output periods; must not contain a period starting at time step 0
    (the radiation needs particle history)"""

    @field_validator("period", mode="after")
    @classmethod
    def _validate_period(cls, period):
        if 0 in map(attrgetter("start"), period.specs):
            raise ValueError(f"The radiation plugin cannot produce output at time step 0. You gave {period=}.")
        return period
