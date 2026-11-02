"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: chillenzer-agents
License: GPLv3+
"""

import re
from pathlib import Path

from picongpu.pypicongpu.species.attribute.registry import ATTRIBUTE_REGISTRY


def _repository_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "include" / "picongpu" / "param" / "speciesAttributes.param"
        if candidate.exists():
            return parent
    raise RuntimeError("Could not locate the PIConGPU source checkout.")


_ATTRIBUTES_PARAM = _repository_root() / "include" / "picongpu" / "param" / "speciesAttributes.param"
_ATTRIBUTES_UNITLESS = _repository_root() / "include" / "picongpu" / "unitless" / "speciesAttributes.unitless"


def _stored_identifiers() -> set[str]:
    text = _ATTRIBUTES_PARAM.read_text()
    # ``value_identifier(TYPE, name, ...)`` / ``value_identifier_func(TYPE, name, ...)``
    return set(re.findall(r"\bvalue_identifier(?:_func)?\(\s*[^,]+,\s*([A-Za-z_]\w*)", text))


def _aliases() -> set[str]:
    return set(re.findall(r"\balias\(\s*([A-Za-z_]\w*)\s*\)", _ATTRIBUTES_PARAM.read_text()))


def _registry_attributes():
    return [cls() for cls in ATTRIBUTE_REGISTRY.values()]


def _stored_registry_identifiers() -> set[str]:
    return {attribute.stored_identifier for attribute in _registry_attributes()}


def test_every_stored_identifier_is_registered_exactly_once():
    stored = _stored_identifiers()
    registered = _stored_registry_identifiers()
    assert stored == registered
    # one entry per stored identifier (two functor names may map to distinct
    # stored identifiers, but no identifier may be registered twice)
    assert len(registered) == len(ATTRIBUTE_REGISTRY)


def test_aliases_and_flags_are_excluded():
    aliases = _aliases()
    assert aliases  # the file does define aliases/flags
    assert aliases.isdisjoint(_stored_registry_identifiers())
    # ``position`` is the one alias intentionally exposed as a functor name.
    assert aliases.isdisjoint(set(ATTRIBUTE_REGISTRY) - {"position"})
    # position is the one alias-like functor name; it maps to the stored identifier
    assert ATTRIBUTE_REGISTRY["position"]().stored_identifier == "position_pic"


def test_every_registered_identifier_has_all_mandatory_traits():
    unitless = _ATTRIBUTES_UNITLESS.read_text()
    for identifier in _stored_registry_identifiers():
        # position_pic is described through the generic ``position<T_Type>``
        # specialisations rather than a ``Unit<position_pic>`` block.
        trait_name = "position<" if identifier == "position_pic" else identifier
        for trait in ("Unit", "UnitDimension", "MacroWeighted", "WeightingPower"):
            assert re.search(rf"struct\s+{trait}<\s*{re.escape(trait_name)}", unitless), (identifier, trait)


def test_registry_metadata_is_complete_and_self_consistent():
    for name, cls in ATTRIBUTE_REGISTRY.items():
        attribute = cls()
        assert attribute.picongpu_name
        assert attribute.cpp_type
        assert attribute.n_components >= 1
        assert len(attribute.unit_dimension) == 7
        assert all(isinstance(component, (int, float)) for component in attribute.unit_dimension)
        assert attribute.unit
        assert isinstance(attribute.macro_weighted, bool)
        assert isinstance(attribute.weighting_power, int)
        assert isinstance(attribute.internal, bool)
        assert name  # functor-facing name


def test_representative_value_types_and_units():
    particle_id = ATTRIBUTE_REGISTRY["particleId"]()
    assert (particle_id.cpp_type, particle_id.n_components) == ("uint64_t", 1)
    assert particle_id.unit_dimension == (0.0,) * 7

    radiation_mask = ATTRIBUTE_REGISTRY["radiationMask"]()
    assert (radiation_mask.cpp_type, radiation_mask.n_components) == ("bool", 1)
    assert radiation_mask.internal

    probe_e = ATTRIBUTE_REGISTRY["probeE"]()
    assert (probe_e.cpp_type, probe_e.n_components) == ("float3_X", 3)
    assert probe_e.unit_dimension == (1.0, 1.0, -3.0, -1.0, 0.0, 0.0, 0.0)
    assert probe_e.unit == "sim.unit.eField()"
    assert probe_e.internal

    probe_b = ATTRIBUTE_REGISTRY["probeB"]()
    assert (probe_b.cpp_type, probe_b.n_components) == ("float3_X", 3)
    assert probe_b.unit_dimension == (0.0, 1.0, -2.0, -1.0, 0.0, 0.0, 0.0)
    assert probe_b.unit == "sim.unit.bField()"

    damping = ATTRIBUTE_REGISTRY["weightingDampingFactor"]()
    assert (damping.cpp_type, damping.n_components, damping.weighting_power) == ("float_X", 1, 0)

    bound = ATTRIBUTE_REGISTRY["charge_state"]()
    assert bound.stored_identifier == "boundElectrons"
    assert (bound.cpp_type, bound.weighting_power) == ("float_X", 1)

    assert ATTRIBUTE_REGISTRY["momentum"]().weighting_power == 1
    assert ATTRIBUTE_REGISTRY["momentumPrev1"]().weighting_power == 1
