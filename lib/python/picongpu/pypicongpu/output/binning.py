"""
This file is part of PIConGPU.
Copyright 2025 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

import json
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_serializer, field_validator, model_validator

from picongpu.pypicongpu.output.timestepspec import TimeStepSpec
from picongpu.pypicongpu.particle_functor.filtered_species import FilteredSpecies
from picongpu.pypicongpu.particle_functor.particle_functor import ParticleFunctor
from picongpu.pypicongpu.particle_functor.translate_to_cpp_type import translate_from_cpp_type
from picongpu.pypicongpu.rendering.renderedobject import RenderedObject
from picongpu.pypicongpu.species import Species
from picongpu.pypicongpu.validation import validate_cpp_identifier


class BinSpec(RenderedObject, BaseModel):
    """
    the binning specification of one axis of the binning diagnostic

    C++ counterpart: the axis::create<kind> arguments of the binning plugin
    (axis::Range {start, stop} and the number of bins nsteps), rendered in
    include/picongpu/param/binningSetup.param.

    Units policy: start/stop in the units of the axis functor's return
    value (e.g. cells for a cell-unit position functor); nsteps is
    dimensionless.
    """

    kind: Literal["Linear", "Log"]
    """the axis type, rendered as the C++ function axis::create{kind}, so it
    must be exactly "Linear" or "Log" (C++: axis::createLinear /
    axis::createLog)"""

    start: int | float
    """range start (the Range min), [axis functor units]; must be < stop"""

    stop: int | float
    """range stop (the Range max), [axis functor units]; must be > start"""

    nsteps: Annotated[int, Field(ge=1)]
    """number of bins, [dimensionless]; must be >= 1"""

    @model_validator(mode="after")
    def _check_range(self):
        if self.start >= self.stop:
            raise ValueError(
                f"The binning range start must be smaller than its stop. You gave start={self.start}, stop={self.stop}."
            )
        if self.kind == "Log" and (self.start == 0 or self.stop == 0 or (self.start < 0) != (self.stop < 0)):
            raise ValueError(
                f"A logarithmic binning range must not include zero. You gave start={self.start}, stop={self.stop}."
            )
        return self


class BinningAxis(RenderedObject, BaseModel):
    """
    one axis of the binning diagnostic

    C++ counterpart: one axis entry in include/picongpu/param/binningSetup.param.

    Units policy: see the bin spec and the axis functor.
    """

    model_config = ConfigDict(populate_by_name=True)

    axis_name: str = Field(alias="name")
    """name of the axis, rendered as the C++ variable axis_{name}, so it must
    be a valid C++ identifier ([A-Za-z0-9_]+)"""

    bin_spec_raw: BinSpec
    """the binning specification as given by the user (pre unit-translation);
    the translated ``bin_spec`` is exposed as a computed field. Kept in the
    serialised form so the model is reconstructable (round-trip safety)."""

    axis_functor: ParticleFunctor = Field(alias="functor")
    """the particle functor computing the axis value"""

    use_overflow_bins: bool
    """if True, values outside the range are counted in overflow bins
    (C++: useOverflowBins)"""

    @computed_field
    def bin_spec(self) -> BinSpec:
        return BinSpec(
            kind=self.bin_spec_raw.kind,
            nsteps=self.bin_spec_raw.nsteps,
            start=translate_from_cpp_type(self.axis_functor.return_type)(self.bin_spec_raw.start),
            stop=translate_from_cpp_type(self.axis_functor.return_type)(self.bin_spec_raw.stop),
        )

    @field_validator("axis_name")
    @classmethod
    def _validate_axis_name(cls, name):
        # The name renders into the C++ variable `axis_{name}`, so the
        # `axis_` prefix makes even a leading digit acceptable.
        return validate_cpp_identifier(name, field="axis_name", prefix="axis_")


class Binning(BaseModel):
    """
    the binning diagnostic (top level)

    C++ counterpart: the binning setup in
    include/picongpu/param/binningSetup.param (one binner function per
    Binning instance).

    Units policy: see the axes, the deposition functor, and the time steps
    (dimensionless).
    """

    model_config = ConfigDict(populate_by_name=True)

    binner_name: str = Field(alias="name")
    """name of the binner, rendered as the C++ function {name}(BinningCreator&),
    so it must be a valid C++ identifier ([A-Za-z_][A-Za-z0-9_]*)"""

    deposition_functor: ParticleFunctor
    """the particle functor computing the deposited quantity"""

    axes: Annotated[list[BinningAxis], Field(min_length=1)]
    """the axes of the histogram; at least one is required"""

    species: Annotated[list[Species | FilteredSpecies], Field(min_length=1)]
    """the species (or filtered species) contributing to the histogram;
    at least one is required"""

    period: TimeStepSpec
    """the time steps at which the histogram is dumped, [time-step number]"""

    openPMDBackendConfig: dict[str, Any] | None = None
    """additional openPMD backend configuration as a JSON-serializable dict
    (C++: setOpenPMDBackendConfig); None = default backend configuration"""

    openPMDExtension: Annotated[str, Field(min_length=1)] | None = Field(default=None, alias="openPMDExt")
    """file extension of the openPMD output (C++: setOpenPMDExtension);
    must not be empty when set"""

    openPMDInfix: str | None = None
    """infix (iteration expansion pattern) of the openPMD filename
    (C++: setOpenPMDInfix)"""

    dumpPeriod: Annotated[int, Field(ge=0)]
    """number of notify periods over which the data is reduced before being
    dumped, [dimensionless]; must be >= 0 (C++: setDumpPeriod, uint32_t)"""

    type_binning: Literal[True] = True
    """tag field identifying the binning diagnostic (discriminator)"""

    @field_serializer("openPMDBackendConfig")
    def _serialize_openPMDBackendConfig(self, value) -> str | None:
        return None if value is None else json.dumps(value)

    @field_validator("openPMDBackendConfig", mode="before")
    @classmethod
    def _deserialize_openPMDBackendConfig(cls, value):
        # the model serializer writes a compact JSON string (inverse of
        # field_serializer above); parse it back on the way in (round-trip
        # safety)
        return None if value is None else (value if isinstance(value, dict) else json.loads(value))

    @field_validator("binner_name")
    @classmethod
    def _validate_binner_name(cls, name):
        # The name renders into the C++ function `{name}(BinningCreator&)`.
        return validate_cpp_identifier(name, field="binner_name")
