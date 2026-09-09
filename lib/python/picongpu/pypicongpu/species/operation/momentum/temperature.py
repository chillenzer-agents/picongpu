"""
This file is part of PIConGPU.
Copyright 2021-2024 PIConGPU contributors
Authors: Hannes Troepgen, Brian Edward Marre
License: GPLv3+
"""

from typing import Annotated

from pydantic import AfterValidator, BeforeValidator, BaseModel, Field, PlainSerializer, model_validator

from ....rendering import RenderedObject

# Note to the future maintainer:
# If you want to add another way to specify the temperature, please turn
# Temperature() into an (abstract) parent class, and add one child class per
# method. (Currently only initialization by giving a temperature in keV is
# supported, so such a structure would be overkill.)


def serialise_vec(value) -> dict:
    return dict(zip("xyz", value))


def deserialise_vec(value):
    # accept the serialised form (dict with x/y/z keys) in addition to the
    # native tuple form, so that model_dump(mode="json") output can be
    # validated again (round-trip safety)
    if isinstance(value, dict):
        try:
            return (value["x"], value["y"], value["z"])
        except KeyError as error:
            raise ValueError(f"Expected a vector with the keys x, y, z. You gave: {value=}.") from error
    return value


def all_ge_0(values):
    wrong = [v < 0 for v in values]
    if any(wrong):
        raise ValueError(
            f"All temperatures must be >= 0 (a negative temperature is unphysical). You gave: {values=}, wrong: {wrong}."
        )
    return values


Vec3_float_temperature = Annotated[
    tuple[float, float, float],
    BeforeValidator(deserialise_vec),
    PlainSerializer(serialise_vec),
    AfterValidator(all_ge_0),
]


class Temperature(RenderedObject, BaseModel):
    """
    Initialize momentum from temperature

    Exactly one of temperature_kev (isotropic) or temperature_kev_directional
    (per-component) must be set.

    C++ counterpart: the initial temperature in
    include/picongpu/param/particle.param.

    Units policy: keV (the C++ interface uses keV, not SI).
    """

    temperature_kev: Annotated[float | None, Field(default=None, gt=0.0)]
    """isotropic temperature, [keV]; must be > 0 when set."""

    temperature_kev_directional: Vec3_float_temperature | None = None
    """per-component temperature (x, y, z) for directional initialization, [keV];
    each component must be >= 0 (0 = cold in that direction)."""

    @model_validator(mode="after")
    def _validate_exactly_one(self):
        scalar_set = self.temperature_kev is not None
        directional_set = self.temperature_kev_directional is not None
        if scalar_set == directional_set:
            raise ValueError("Exactly one of temperature_kev or temperature_kev_directional must be set")
        return self
