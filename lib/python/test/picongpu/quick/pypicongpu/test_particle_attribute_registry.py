"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: chillenzer-agents
License: GPLv3+
"""

import re
from pathlib import Path

from picongpu.pypicongpu.species.attribute.registry import ATTRIBUTE_REGISTRY

# Exact metadata per functor-facing name.  Mirrors
# include/picongpu/unitless/speciesAttributes.unitless; the C++ ``position<T>``
# trait describes the stored in-cell value, while the functor exposes it in a
# selectable unit (handled separately in the picmi layer).
EXPECTED_METADATA = {
    "position": (
        "floatD_X",
        3,
        "sim.pic.getCellSize() * sim.unit.length()",
        (1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        False,
        0,
        False,
    ),
    "particleId": ("uint64_t", 1, "1.", (0.0,) * 7, False, 0, False),
    "momentum": (
        "float3_X",
        3,
        "sim.unit.mass() * sim.unit.speed()",
        (1.0, 1.0, -1.0, 0.0, 0.0, 0.0, 0.0),
        True,
        1,
        False,
    ),
    "momentumPrev1": (
        "float3_X",
        3,
        "sim.unit.mass() * sim.unit.speed()",
        (1.0, 1.0, -1.0, 0.0, 0.0, 0.0, 0.0),
        True,
        1,
        False,
    ),
    "weighting": ("float_X", 1, "1.", (0.0,) * 7, True, 1, False),
    "weightingDampingFactor": ("float_X", 1, "1.", (0.0,) * 7, False, 0, False),
    "probeE": ("float3_X", 3, "sim.unit.eField()", (1.0, 1.0, -3.0, -1.0, 0.0, 0.0, 0.0), False, 0, True),
    "probeB": ("float3_X", 3, "sim.unit.bField()", (0.0, 1.0, -2.0, -1.0, 0.0, 0.0, 0.0), False, 0, True),
    "radiationMask": ("bool", 1, "1.", (0.0,) * 7, False, 0, True),
    "transitionRadiationMask": ("bool", 1, "1.", (0.0,) * 7, False, 0, True),
    "charge_state": ("float_X", 1, "1.", (0.0,) * 7, False, 1, False),
    "atomicStateCollectionIndex": ("uint32_t", 1, "1.", (0.0,) * 7, False, 0, True),
    "processClass": ("uint8_t", 1, "1.", (0.0,) * 7, False, 0, True),
    "transitionIndex": ("uint32_t", 1, "1.", (0.0,) * 7, False, 0, True),
    "binIndex": ("uint32_t", 1, "1.", (0.0,) * 7, False, 0, True),
    "accepted": ("bool", 1, "1.", (0.0,) * 7, False, 0, True),
    "totalCellIdx": ("DataSpace<simDim>", 3, "1.", (0.0,) * 7, False, 0, False),
}


def _repository_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "include" / "picongpu" / "param" / "speciesAttributes.param"
        if candidate.exists():
            return parent
    raise RuntimeError("Could not locate the PIConGPU source checkout.")


_ATTRIBUTES_PARAM = _repository_root() / "include" / "picongpu" / "param" / "speciesAttributes.param"
_ATTRIBUTES_UNITLESS = _repository_root() / "include" / "picongpu" / "unitless" / "speciesAttributes.unitless"

# The type may itself contain commas inside template argument lists, so match a
# sequence of non-comma tokens and balanced angle/parenthesis groups.
_VALUE_IDENTIFIER = re.compile(r"\bvalue_identifier(?:_func)?\(\s*(?:[^<>(),]+|<[^<>]*>|\([^()]*\))+,\s*([A-Za-z_]\w*)")


def _stored_identifiers() -> list[str]:
    return _VALUE_IDENTIFIER.findall(_ATTRIBUTES_PARAM.read_text())


def _aliases() -> set[str]:
    return set(re.findall(r"\balias\(\s*([A-Za-z_]\w*)\s*\)", _ATTRIBUTES_PARAM.read_text()))


def _registry_attributes():
    return [cls() for cls in ATTRIBUTE_REGISTRY.values()]


def _stored_registry_identifiers() -> set[str]:
    return {attribute.stored_identifier for attribute in _registry_attributes()}


def test_every_stored_identifier_is_registered_exactly_once():
    found = _stored_identifiers()
    stored = set(found)
    registered = _stored_registry_identifiers()
    assert stored == registered
    # one entry per stored identifier (two functor names may map to distinct
    # stored identifiers, but no identifier may be registered twice)
    assert len(registered) == len(ATTRIBUTE_REGISTRY)
    # no identifier is silently skipped or counted twice
    assert len(found) == len(stored) == len(ATTRIBUTE_REGISTRY) == 17


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


def test_registry_metadata_matches_expected_table():
    assert set(EXPECTED_METADATA) == set(ATTRIBUTE_REGISTRY)
    for name, expected in EXPECTED_METADATA.items():
        attribute = ATTRIBUTE_REGISTRY[name]()
        actual = (
            attribute.cpp_type,
            attribute.n_components,
            attribute.unit,
            attribute.unit_dimension,
            attribute.macro_weighted,
            attribute.weighting_power,
            attribute.internal,
        )
        assert actual == expected, (name, actual, expected)


def test_stored_value_type_matches_attributes_param():
    text = _ATTRIBUTES_PARAM.read_text()
    for attribute in _registry_attributes():
        identifier = attribute.stored_identifier
        match = re.search(
            rf"\bvalue_identifier(?:_func)?\(\s*([^,]+),\s*{re.escape(identifier)}\b",
            text,
        )
        assert match, identifier
        # position is controlled by the position<T> alias machinery
        if identifier != "position_pic":
            assert match.group(1).strip() == attribute.cpp_type, (identifier, match.group(1))
