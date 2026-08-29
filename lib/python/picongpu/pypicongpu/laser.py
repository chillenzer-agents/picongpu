"""
This file is part of PIConGPU.
Copyright 2021-2024 PIConGPU contributors
Authors: Hannes Troepgen, Brian Edward Marre, Alexander Debus, Julian Lenz
License: GPLv3+
"""

import logging
from enum import Enum
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    PlainSerializer,
    computed_field,
    model_validator,
)

from picongpu.pypicongpu.units import SI


class PolarizationType(Enum):
    """represents a polarization of a laser (for PIConGPU)"""

    LINEAR = "Linear"
    CIRCULAR = "Circular"


def _get_huygens_surface_serialized(huygens_surface_positions) -> dict:
    """Serialize huygens surface positions for all laser types"""
    return {
        "row_x": {
            "negative": huygens_surface_positions[0][0],
            "positive": huygens_surface_positions[0][1],
        },
        "row_y": {
            "negative": huygens_surface_positions[1][0],
            "positive": huygens_surface_positions[1][1],
        },
        "row_z": {
            "negative": huygens_surface_positions[2][0],
            "positive": huygens_surface_positions[2][1],
        },
    }


def deserialise_huygens(value):
    # accept the serialised form (nested dict with row_x/row_y/row_z) in
    # addition to the native 3x2 list form, so that model_dump(mode="json")
    # output can be validated again (round-trip safety)
    if isinstance(value, dict):
        try:
            return [[value[f"row_{axis}"]["negative"], value[f"row_{axis}"]["positive"]] for axis in ("x", "y", "z")]
        except (KeyError, TypeError) as error:
            raise ValueError(f"Expected a serialised huygens surface position. You gave: {value=}.") from error
    return value


class _Component(BaseModel):
    """single (float) component of a 3D vector argument (direction/position)"""

    component: float
    """vector component value"""

    def __eq__(self, other):
        if isinstance(other, float) or isinstance(other, int):
            return self.component == other
        return super().__eq__(other)


def validate_component_vector(value):
    try:
        return [_Component(component=c) for c in value]
    except Exception:
        return value


class _BaseLaser(BaseModel):
    """
    Base class for all laser types with common properties and serialization logic

    C++ counterpart: include/picongpu/param/incidentField.param
    (one background field profile per laser).

    Units policy: SI (m for lengths, s for times, V/m for E0, rad for phases).
    """

    # accept both the field names (as produced by model_dump) and the aliases
    # (e.g. wavelength) upon construction, so that serialised output can be
    # validated again (round-trip safety)
    model_config = ConfigDict(populate_by_name=True)

    # Common properties for all lasers
    propagation_direction: Annotated[
        tuple[_Component, _Component, _Component], BeforeValidator(validate_component_vector)
    ]
    """propagation direction, [dimensionless] (normalized vector)"""
    polarization_direction: Annotated[
        tuple[_Component, _Component, _Component], BeforeValidator(validate_component_vector)
    ]
    """direction of polarization, [dimensionless] (normalized vector)"""
    polarization_type: PolarizationType
    """laser polarization (Linear or Circular)"""
    wave_length_si: Annotated[float, Field(alias="wavelength", gt=0.0), SI("m")]
    """wave length, [m]; must be > 0.
    C++ name: lambda_SI (incidentField.param)."""
    pulse_duration_si: Annotated[float, Field(alias="duration", gt=0.0), SI("s")]
    """pulse duration, [s] (1 sigma of a standard gaussian for the intensity (E^2)); must be > 0.
    C++ name: pulselength_SI (incidentField.param)."""
    focus_pos_si: Annotated[tuple[_Component, _Component, _Component], BeforeValidator(validate_component_vector)] = (
        Field(alias="focal_position")
    )
    """focus position vector, [m].
    C++ name: focus_SI (incidentField.param)."""
    phase: Annotated[float, Field(alias="phi0"), SI("rad")]
    """initial phase phi0, [rad]; periodic in 2*pi.
    C++ name: PHI (incidentField.param)."""
    E0_si: Annotated[float, Field(alias="E0", gt=0.0), SI("V/m")]
    """peak electric field amplitude, [V/m]; must be > 0 (an E0 of 0 would
    switch the laser off, which is expressed by omitting the laser).
    C++ name: AMPLITUDE_SI (incidentField.param)."""
    pulse_init: Annotated[float, Field(ge=0.0)]
    """laser will be initialized pulse_init times of duration (unitless); must be >= 0.
    C++ name: PULSE_INIT (incidentField.param)."""

    # Huygens surface position (common to all lasers)
    huygens_surface_positions: Annotated[
        list[list[int]],
        BeforeValidator(deserialise_huygens),
        PlainSerializer(_get_huygens_surface_serialized),
    ]
    """Position in cells of the Huygens surface relative to start/
       edge(negative numbers) of the total domain, [cells];
       a 3x2 list: per axis (positive edge, negative edge).
       C++ name: huygens surface positions (incidentField.param)."""

    def _get_common_serialized_fields(self) -> dict:
        """Get all common serialized fields for lasers"""
        return self.model_dump(mode="json")


def all_ge(values, than_value):
    if any(wrong := [x < than_value for x in values]):
        logging.warning(f"All {values=} should be greater or equal {than_value=}. The following are {wrong=}.")
    return values


def serialise_laguerre(values, suffix):
    return [{f"single_laguerre_{suffix}": x} for x in values]


class GaussianLaser(_BaseLaser):
    """
    PIConGPU Gaussian Laser

    Holds Parameters to specify a gaussian laser

    C++ counterpart: the Gaussian profile in
    include/picongpu/param/incidentField.param.

    Units policy: SI (m for lengths, s for times, V/m for E0, rad for phases);
    Laguerre mode magnitudes/phases are dimensionless.
    """

    type_gaussian: Literal[True] = True
    """discriminator for the AnyLaser union."""

    waist_si: Annotated[float, Field(alias="waist", gt=0.0), SI("m")]
    """beam waist, [m]; must be > 0.
    C++ name: W0_SI (incidentField.param)."""
    laguerre_modes: Annotated[list[_Component], BeforeValidator(validate_component_vector)] = Field(min_length=1)
    """array containing the magnitudes of radial Laguerre-modes, [dimensionless];
    must have at least 1 entry and equal length to laguerre_phases."""
    laguerre_phases: Annotated[list[_Component], BeforeValidator(validate_component_vector)] = Field(min_length=1)
    """array containing the phases of radial Laguerre-modes, [rad];
    must have at least 1 entry and equal length to laguerre_modes."""

    @computed_field
    def modenumber(self) -> int:
        return len(self.laguerre_modes) - 1

    @model_validator(mode="after")
    def check(self):
        if len(self.laguerre_phases) != len(self.laguerre_modes):
            raise ValueError("Laguerre modes and Laguerre phases MUST BE arrays of equal length.")
        return self


class PlaneWaveLaser(_BaseLaser):
    """
    PIConGPU Plane Wave Laser

    Holds Parameters to specify a plane wave laser

    C++ counterpart: the plane wave profile in
    include/picongpu/param/incidentField.param.

    Units policy: SI (see _BaseLaser).
    """

    type_planewave: Literal[True] = True
    """discriminator for the AnyLaser union."""

    laser_nofocus_constant_si: float
    """constant for plane wave laser without focus, [dimensionless].
    C++ name: LASER_NOFOCUS_CONSTANT_SI (incidentField.param)."""


class DispersivePulseLaser(_BaseLaser):
    """
    PIConGPU Dispersive Pulse Laser

    Holds Parameters to specify a dispersive Gaussian laser pulse with dispersion parameters

    C++ counterpart: the dispersive pulse profile in
    include/picongpu/param/incidentField.param.

    Units policy: SI (m for lengths, s for times); the dispersion parameters
    carry their respective SI units (see the fields).
    """

    type_dispersive: Literal[True] = True
    """discriminator for the AnyLaser union."""

    waist_si: Annotated[float, Field(alias="waist", gt=0.0), SI("m")]
    """beam waist, [m]; must be > 0.
    C++ name: W0_SI (incidentField.param)."""
    spectral_support: Annotated[float, Field(gt=0.0)]
    """width of the spectral support for the discrete Fourier transform,
    [dimensionless]; must be > 0."""
    sd_si: Annotated[float, SI("m*s")]
    """spatial dispersion in focus, [m*s].
    C++ name: SD_SI (incidentField.param)."""
    ad_si: Annotated[float, SI("rad*s")]
    """angular dispersion in focus, [rad*s].
    C++ name: AD_SI (incidentField.param)."""
    gdd_si: Annotated[float, SI("s^2")]
    """group velocity dispersion in focus, [s^2].
    C++ name: GDD_SI (incidentField.param)."""
    tod_si: Annotated[float, SI("s^3")]
    """third order dispersion in focus, [s^3].
    C++ name: TOD_SI (incidentField.param)."""


class FromOpenPMDPulseLaser(BaseModel):
    """
    PIConGPU FromOpenPMDPulseLaser

    Holds Parameters to specify a laser pulse from an OpenPMD file

    C++ counterpart: the FromOpenPMDPulse profile in
    include/picongpu/param/incidentField.param.

    Units policy: SI (m for lengths, s for times); iteration is a count.
    """

    type_fromOpenPMDPulse: Literal[True] = True
    """discriminator for the AnyLaser union."""

    propagation_direction: Annotated[
        tuple[_Component, _Component, _Component], BeforeValidator(validate_component_vector)
    ]
    """propagation direction, [dimensionless] (normalized vector)"""
    polarization_direction: Annotated[
        tuple[_Component, _Component, _Component], BeforeValidator(validate_component_vector)
    ]
    """direction of polarization, [dimensionless] (normalized vector)"""
    file_path: Annotated[str, Field(min_length=1)]
    """File path to the OpenPMD file containing the pulse data, [path]; must not be empty.
    C++ name: file (incidentField.param)."""
    iteration: Annotated[int, Field(ge=0)]
    """Iteration in the OpenPMD file to use, [dimensionless count]; must be >= 0
    (rendered as a uint32_t).
    C++ name: iteration (incidentField.param)."""
    dataset_name: str
    """Name of the dataset in the OpenPMD file containing the pulse data.
    C++ name: datasetEName (incidentField.param)."""
    datatype: str
    """Data type of the pulse data (openPMD type name).
    C++ name: datatype (incidentField.param)."""
    time_offset_si: Annotated[float, SI("s")]
    """Time offset in seconds to apply to the pulse data, [s].
    C++ name: timeOffset (incidentField.param)."""
    polarisationAxisOpenPMD: str
    """Polarization axis name in the OpenPMD file.
    C++ name: polarisationAxisOpenPMD (incidentField.param)."""
    propagationAxisOpenPMD: str
    """Propagation axis name in the OpenPMD file.
    C++ name: propagationAxisOpenPMD (incidentField.param)."""
    huygens_surface_positions: Annotated[list[list[int]], PlainSerializer(_get_huygens_surface_serialized)]
    """Position in cells of the Huygens surface relative to start/
       edge(negative numbers) of the total domain, [cells];
       a 3x2 list: per axis (positive edge, negative edge)."""


class TWTSLaser(_BaseLaser):
    """
    PIConGPU TWTSLaser

    Holds Parameters to specify a TWTS laser pulse

    C++ counterpart: the TWTS profile in
    include/picongpu/param/incidentField.param.

    Units policy: SI (m for lengths, s for times, rad for angles);
    beta0 is normalized to the speed of light, the window parameters are
    time-step numbers.
    """

    type_twts: Literal[True] = True
    """discriminator for the AnyLaser union."""

    waist_si: Annotated[float, Field(alias="waist", gt=0.0), SI("m")]
    """beam waist, [m]; must be > 0.
    C++ name: W0_SI (incidentField.param)."""
    laserIncidenceAngle: Annotated[float, SI("rad")]
    """Laser incident angle, [rad] denoting the mean laser phase
       propagation direction with respect to the y-axis.
       C++ name: PHI (incidentField.param)."""
    laserIncidenceAnglePositive: bool
    """Is the laser incidence angle positive?, [dimensionless flag].
    C++ name: phiPositive (incidentField.param)."""
    polarizationAngle: Annotated[float, SI("rad")]
    """Linear laser polarization direction,
       parameterized as a rotation angle, [rad]
       of the x-direction around the mean
       laser phase propagation direction.
       C++ name: POLARIZATION_ANGLE (incidentField.param)."""
    beta0: Annotated[float, Field(ge=-1.0, le=1.0)]
    """speed of the TWTS laser overlap (focal region) normalized to the vacuum
    speed of light, [dimensionless]; must satisfy |beta0| <= 1 (the default
    1.0 = overlap propagates with c).
    C++ name: BETA_0 (incidentField.param)."""
    time_offset_si: Annotated[float, SI("s")]
    """time offset to apply to the pulse, [s].
    C++ name: tdelay_user_SI (incidentField.param)."""
    focus_lateral_offset_si: Annotated[float, SI("m")]
    """Offset from the middle of the simulation domain
       to the laser focus in z-direction, [m].
       C++ name: focus_lateral_offset (incidentField.param)."""
    windowStart: Annotated[float, Field(ge=0.0)]
    """First time step number at which the laser starts to be gradually switched on
    using a Blackman-Nuttall window, [dimensionless time-step number]; must be >= 0.
    A window of length 0 deactivates the switching (laser always present).
    C++ name: windowStart (incidentField.param)."""
    windowEnd: Annotated[float, Field(ge=0.0)]
    """Final time step number after gradually switching off the laser using a
    Blackman-Nuttall window, [dimensionless time-step number]; must be >= 0 and,
    when the window is active (windowLength > 0), > windowStart.
    C++ name: windowEnd (incidentField.param)."""
    windowLength: Annotated[float, Field(ge=0.0)]
    """Switching duration by half a Blackman-Nuttall window in number of time steps,
    [dimensionless time-step number]; must be >= 0 (0 deactivates the window).
    C++ name: windowLength (incidentField.param)."""
    huygens_surface_positions: Annotated[list[list[int]], PlainSerializer(_get_huygens_surface_serialized)]
    """Position in cells of the Huygens surface relative to start/
       edge(negative numbers) of the total domain, [cells];
       a 3x2 list: per axis (positive edge, negative edge)."""

    @model_validator(mode="after")
    def _check_window(self):
        if self.windowLength > 0 and self.windowEnd <= self.windowStart:
            raise ValueError(
                "With an active window (windowLength > 0) windowEnd must be greater than windowStart. "
                f"You gave: {self.windowStart=}, {self.windowEnd=}, {self.windowLength=}."
            )
        return self


AnyLaser = DispersivePulseLaser | FromOpenPMDPulseLaser | GaussianLaser | PlaneWaveLaser | TWTSLaser
