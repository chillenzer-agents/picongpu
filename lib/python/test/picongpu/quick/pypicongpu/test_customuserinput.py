"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
License: GPLv3+
"""

import pytest
from pydantic import ValidationError

from picongpu.pypicongpu.customuserinput import MAX_NESTING_DEPTH, CustomUserInput

_JSON_SERIALISABLE_VALUES = [
    True,
    42,
    1.5,
    "some string",
    None,
    [1, "x", None, [2, 3]],
    {"key": [1, {"nested": 2.5}]},
]

_NON_JSON_SERIALISABLE_VALUES = [
    pytest.param(lambda x: x, id="callable"),
    pytest.param({1, 2, 3}, id="set"),
    pytest.param((1, 2), id="tuple"),
    pytest.param(b"bytes", id="bytes"),
    pytest.param(object(), id="arbitrary_object"),
]


@pytest.mark.parametrize("value", _JSON_SERIALISABLE_VALUES)
def test_json_serialisable_values_accepted(value):
    # must not raise
    CustomUserInput(rendering_context={"value": value})


@pytest.mark.parametrize("value", _NON_JSON_SERIALISABLE_VALUES)
def test_non_json_serialisable_values_rejected_at_construction(value):
    with pytest.raises(ValidationError, match="JSON-serialisable"):
        CustomUserInput(rendering_context={"value": value})


@pytest.mark.parametrize("value", _NON_JSON_SERIALISABLE_VALUES)
def test_non_json_serialisable_values_rejected_by_add_to_custom_input(value):
    custom_input = CustomUserInput()
    with pytest.raises(ValueError, match="JSON-serialisable"):
        custom_input.addToCustomInput({"value": value}, "some_tag")


def test_callable_raises_clear_error_at_construction():
    message = "JSON-serialisable"
    with pytest.raises(ValidationError, match=message):
        CustomUserInput(rendering_context={"x": lambda x: x})
    custom_input = CustomUserInput()
    with pytest.raises(ValueError, match=message):
        custom_input.addToCustomInput({"x": lambda x: x}, "tag")


def test_nested_bad_value_reports_location():
    with pytest.raises(ValidationError, match="function"):
        CustomUserInput(rendering_context={"nested": {"bad": lambda x: x}})


def test_per_entry_form_roundtrips():
    custom_input = CustomUserInput()
    custom_input.addToCustomInput({"test_data_1": 1, "nested": {"k": [1, 2, 3]}}, "tag_1")
    custom_input.addToCustomInput({"test_data_2": 2}, "tag_2")

    dumped = custom_input.model_dump(mode="json")
    assert dumped == {
        "tags": ["tag_1", "tag_2"],
        "rendering_context": {"test_data_1": 1, "nested": {"k": [1, 2, 3]}, "test_data_2": 2},
    }

    restored = CustomUserInput.model_validate(dumped)
    assert restored.tags == custom_input.tags
    assert restored.rendering_context == custom_input.rendering_context
    assert restored.model_dump(mode="json") == dumped


def test_empty_entry_serialises_to_none():
    # a fully unset entry carries no payload and serialises to None
    assert CustomUserInput().model_dump(mode="json") is None


def test_accepts_per_entry_serialised_form():
    restored = CustomUserInput.model_validate({"tags": ["tag_1"], "rendering_context": {"test_data_1": 1}})
    assert restored.tags == ["tag_1"]
    assert restored.rendering_context == {"test_data_1": 1}


def test_accepts_flat_merged_form():
    # the flattened form produced by Simulation's customuserinput field
    # serializer: "tags" plus the (merged) rendering context keys at the top level
    restored = CustomUserInput.model_validate(
        {"tags": ["tag_1", "tag_2"], "test_data_1": 1, "nested": {"k": [1, 2, 3]}}
    )
    assert restored.tags == ["tag_1", "tag_2"]
    assert restored.rendering_context == {"test_data_1": 1, "nested": {"k": [1, 2, 3]}}


def test_rejects_callable_assigned_after_construction():
    # whole-dict reassignment of the rendering context is validated eagerly
    custom_input = CustomUserInput(rendering_context={"x": 1})
    with pytest.raises(ValidationError, match="JSON-serialisable"):
        custom_input.rendering_context = {"x": lambda x: x}


def test_none_assigned_after_construction_is_allowed():
    custom_input = CustomUserInput(rendering_context={"x": 1})
    custom_input.rendering_context = None
    assert custom_input.rendering_context is None


def test_in_place_mutation_rejected_at_dump():
    # in-place mutation of the exposed dict cannot be intercepted by assignment
    # validation, so dumping re-validates and raises a clear error instead of
    # the opaque PydanticSerializationError
    custom_input = CustomUserInput(rendering_context={"x": 1})
    custom_input.rendering_context["x"] = lambda x: x
    with pytest.raises(ValueError, match="JSON-serialisable"):
        custom_input.model_dump(mode="json")


def test_in_place_mutation_of_nested_dict_rejected_at_dump():
    custom_input = CustomUserInput(rendering_context={"nested": {"k": 1}})
    custom_input.rendering_context["nested"]["k"] = {1, 2}
    with pytest.raises(ValueError, match="JSON-serialisable"):
        custom_input.model_dump(mode="json")


def test_non_string_dict_key_rejected():
    with pytest.raises(ValidationError, match="keys must be strings"):
        CustomUserInput(rendering_context={"nested": {(1, 2): "value"}})


def test_non_finite_float_rejected():
    with pytest.raises(ValidationError, match="not a finite number"):
        CustomUserInput(rendering_context={"x": float("nan")})
    with pytest.raises(ValidationError, match="not a finite number"):
        CustomUserInput(rendering_context={"x": float("inf")})


def test_too_deeply_nested_input_rejected_with_clear_error():
    value = 0
    for _ in range(MAX_NESTING_DEPTH + 2):
        value = {"k": value}
    with pytest.raises(ValidationError, match="nested too deeply"):
        CustomUserInput(rendering_context=value)
