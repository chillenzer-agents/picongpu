"""
This file is part of PIConGPU.
Copyright 2021-2024 PIConGPU contributors
Authors: Hannes Troepgen, Brian Edward Marre, Alexander Debus, Julian Lenz
License: GPLv3+
"""

from enum import Enum
from functools import partial
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    Field,
    PlainSerializer,
    computed_field,
    model_validator,
)

from .validation import component_vector, same_length
from .vector import deserialise_huygens, serialise_huygens, serialise_vec


class PolarizationType(Enum):
    """represents a polarization of a laser (for PIConGPU)"""

    LINEAR = "Linear"
    CIRCULAR = "Circular"


def _component_vector_field(field: str):
    return partial(component_vector, field=field)


class _BaseLaser(BaseModel):
    """Base class for all laser types with common properties and serialization logic"""

    # Common properties for all lasers
    propagation_direction: Annotated[
        tuple[float, float, float],
        BeforeValidator(_component_vector_field("propagation_direction")),
        PlainSerializer(serialise_vec),
    ]
    """propagation direction (normalized vector)"""
    polarization_direction: Annotated[
        tuple[float, float, float],
        BeforeValidator(_component_vector_field("polarization_direction")),
        PlainSerializer(serialise_vec),
    ]
    """direction of polarization (normalized vector)"""
    polarization_type: PolarizationType
    """laser polarization"""
    wave_length_si: float = Field(alias="wavelength", gt=0.0)
    """wave length in m"""
    pulse_duration_si: float = Field(alias="duration", gt=0.0)
    """duration in s (1 sigma of a standard gaussian for the intensity (E^2))"""
    focus_pos_si: Annotated[
        tuple[float, float, float],
        BeforeValidator(_component_vector_field("focus_pos_si")),
        PlainSerializer(serialise_vec),
    ] = Field(alias="focal_position")
    """focus position vector in m"""
    phase: float = Field(alias="phi0")
    """phi0 in rad, periodic in 2*pi"""
    E0_si: float = Field(alias="E0", gt=0.0)
    """E0 in V/m"""
    pulse_init: float = Field(ge=0.0)
    """laser will be initialized pulse_init times of duration (unitless)"""

    # Huygens surface position (common to all lasers)
    huygens_surface_positions: Annotated[
        list[list[int]],
        BeforeValidator(deserialise_huygens),
        PlainSerializer(serialise_huygens),
    ]
    """Position in cells of the Huygens surface relative to start/
       edge(negative numbers) of the total domain"""

    def _get_common_serialized_fields(self) -> dict:
        """Get all common serialized fields for lasers"""
        return self.model_dump(mode="json")


class GaussianLaser(_BaseLaser):
    """
    PIConGPU Gaussian Laser

    Holds Parameters to specify a gaussian laser
    """

    type_gaussian: Literal[True] = True

    waist_si: float = Field(alias="waist", gt=0.0)
    """beam waist in m"""
    laguerre_modes: list[float] = Field(min_length=1)
    """array containing the magnitudes of radial Laguerre-modes"""
    laguerre_phases: list[float] = Field(min_length=1)
    """array containing the phases of radial Laguerre-modes"""

    @computed_field
    def modenumber(self) -> int:
        return len(self.laguerre_modes) - 1

    @model_validator(mode="after")
    def check(self):
        same_length(
            self.laguerre_phases,
            self.laguerre_modes,
            a_field="laguerre_phases",
            b_field="laguerre_modes",
        )
        return self


class PlaneWaveLaser(_BaseLaser):
    """
    PIConGPU Plane Wave Laser

    Holds Parameters to specify a plane wave laser
    """

    type_planewave: Literal[True] = True
    laser_nofocus_constant_si: float
    """constant for plane wave laser without focus (unitless)"""


class DispersivePulseLaser(_BaseLaser):
    """
    PIConGPU Dispersive Pulse Laser

    Holds Parameters to specify a dispersive Gaussian laser pulse with dispersion parameters
    """

    type_dispersive: Literal[True] = True

    waist_si: float = Field(alias="waist")
    """beam waist in m"""
    spectral_support: float
    """width of the spectral support for the discrete Fourier transform [none]"""
    sd_si: float
    """spatial dispersion in focus [m*s]"""
    ad_si: float
    """angular dispersion in focus [rad*s]"""
    gdd_si: float
    """group velocity dispersion in focus [s^2]"""
    tod_si: float
    """third order dispersion in focus [s^3]"""


class FromOpenPMDPulseLaser(BaseModel):
    """
    PIConGPU FromOpenPMDPulseLaser

    Holds Parameters to specify a laser pulse from an OpenPMD file
    """

    type_fromOpenPMDPulse: Literal[True] = True

    propagation_direction: Annotated[
        tuple[float, float, float],
        BeforeValidator(_component_vector_field("propagation_direction")),
        PlainSerializer(serialise_vec),
    ]
    """propagation direction (normalized vector)"""
    polarization_direction: Annotated[
        tuple[float, float, float],
        BeforeValidator(_component_vector_field("polarization_direction")),
        PlainSerializer(serialise_vec),
    ]
    """direction of polarization (normalized vector)"""
    file_path: str
    """File path to the OpenPMD file containing the pulse data"""
    iteration: int
    """Iteration in the OpenPMD file to use"""
    dataset_name: str
    """Name of the dataset in the OpenPMD file containing the pulse data"""
    datatype: str
    """Data type of the pulse data"""
    time_offset_si: float
    """Time offset in seconds to apply to the pulse data [s]"""
    polarisationAxisOpenPMD: str
    """Polarization axis name in the OpenPMD file"""
    propagationAxisOpenPMD: str
    """Propagation axis name in the OpenPMD file"""
    huygens_surface_positions: Annotated[
        list[list[int]],
        BeforeValidator(deserialise_huygens),
        PlainSerializer(serialise_huygens),
    ]
    """Position in cells of the Huygens surface relative to start/
       edge(negative numbers) of the total domain"""


class TWTSLaser(_BaseLaser):
    """
    PIConGPU TWTSLaser

    Holds Parameters to specify a TWTS laser pulse
    """

    type_twts: Literal[True] = True

    waist_si: float = Field(alias="waist")
    """beam waist in m"""
    laserIncidenceAngle: float
    """Laser incident angle [rad] denoting the mean laser phase
       propagation direction with respect to the y-axis"""
    laserIncidenceAnglePositive: bool
    """Is the laser incidence angle positive?"""
    polarizationAngle: float
    """Linear laser polarization direction
       parameterized as a rotation angle [rad]
       of the x-direction around the mean
       laser phase propagation direction"""
    beta0: float
    """speed of focal region normalized to the vacuum speed of light [dimensionless]"""
    time_offset_si: float
    """time offset to apply to the pulse [s]"""
    focus_lateral_offset_si: float
    """Offset from the middle of the simulation domain
       to the laser focus in z-direction [m]."""
    windowStart: float
    """First time step number [#] at which the laser starts to be gradually switched on using a Blackman-Nuttall window"""
    windowEnd: float
    """Final time step number [#] after gradually switching off the laser using a Blackman-Nuttall window"""
    windowLength: float
    """Denotes the respective switching duration by half a Blackman-Nuttall window in number of time steps unit [#]"""
    huygens_surface_positions: Annotated[
        list[list[int]],
        BeforeValidator(deserialise_huygens),
        PlainSerializer(serialise_huygens),
    ]
    """Position in cells of the Huygens surface relative to start/
       edge(negative numbers) of the total domain"""


AnyLaser = DispersivePulseLaser | FromOpenPMDPulseLaser | GaussianLaser | PlaneWaveLaser | TWTSLaser
