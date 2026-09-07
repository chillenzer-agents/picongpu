"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+

Tests for the exploratory unit-annotation PoC
(``picongpu.pypicongpu.units``, see ``docs/source/dev/units_design.rst``).

Free-function pytest per STYLE-GUIDE B8-B10.
"""

import pytest
from picongpu.pypicongpu.particle_functor.unit_dimension import (
    UnitDimension as PypicParticleFunctorUnitDimension,
)
from picongpu.pypicongpu.species.constant.mass import Mass
from picongpu.pypicongpu.units import Unit, convert, to_unit_dimension
from pint.errors import DimensionalityError
from pydantic import ValidationError


def test_dimension_of_m():
    assert to_unit_dimension("m") == [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]


def test_dimension_of_inverse_cube():
    assert to_unit_dimension("m**-3") == [-3.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]


def test_dimension_of_keV():
    # energy: L^2 M^1 T^-2
    assert to_unit_dimension("keV") == [2.0, 1.0, -2.0, 0.0, 0.0, 0.0, 0.0]


def test_dimension_of_dimensionless():
    assert to_unit_dimension("1") == [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]


def test_to_unit_dimension_fed_to_particle_functor_unit_dimension():
    # the pint-derived 7-vector slots directly into the existing, C++-consumed
    # pypicongpu UnitDimension (functor unification direction of the design)
    functor_dimension = PypicParticleFunctorUnitDimension(unit_dimension=to_unit_dimension("kg*m/s"))
    assert functor_dimension.unit_dimension == [1.0, 1.0, -1.0, 0.0, 0.0, 0.0, 0.0]


def test_convert_keV_to_j():
    # exact value after the 2019 SI redefinition: 1 keV = 1.602176634e-16 J
    assert convert(1, "keV", "J") == pytest.approx(1.602176634e-16)


def test_convert_length_scale():
    assert convert(1, "m", "cm") == pytest.approx(100.0)


def test_convert_incompatible_dimensions_raises():
    with pytest.raises(DimensionalityError):
        convert(1, "m", "s")


def test_unit_metadata_roundtrip():
    unit = Unit("kg")
    assert unit.dimension == [0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    # reconstruct from its own description
    reconstructed = Unit(unit.unit, unit.scale)
    assert reconstructed == unit
    assert reconstructed.dimension == unit.dimension


def test_unit_metadata_distinguishes_scale():
    # scale is part of the machine-readable payload
    assert Unit("keV", scale="keV").scale == "keV"
    assert Unit("keV", scale="keV") != Unit("keV", scale="SI")


def test_annotated_unit_is_metadata_only():
    # Unit adds no validation/serialisation: a negative mass still fails on the
    # pre-existing ge=0.0 constraint, not on any unit logic
    with pytest.raises(ValidationError):
        Mass(mass_si=-1.0)


def test_pilot_field_schema_carries_unit():
    schema = Mass.model_json_schema()
    mass_schema = schema["properties"]["mass_si"]
    assert mass_schema["unit"] == "kg"
    assert mass_schema["unit_scale"] == "SI"
    assert mass_schema["unit_dimension"] == [0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0]


def test_pilot_field_value_dump_unchanged():
    # the annotation must not leak into the serialised value
    assert Mass(mass_si=1e-27).model_dump(mode="json") == {"mass_si": 1e-27}


def test_pilot_field_roundtrip():
    mass = Mass(mass_si=1e-27)
    assert Mass.model_validate(mass.model_dump(mode="json")) == mass
