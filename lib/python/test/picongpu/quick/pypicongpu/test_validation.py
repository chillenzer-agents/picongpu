"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: opencode
License: GPLv3+
"""

from picongpu.pypicongpu.validation import (
    all_positive,
    as_list,
    at_least_one_of,
    component_vector,
    exactly_one,
    in_unit_interval,
    less_than,
    non_negative,
    positive,
    radius_larger_than,
    same_length,
    unit_vector,
    validate_cpp_identifier,
)
from pytest import raises


def test_validate_cpp_identifier():
    validate_cpp_identifier("valid_name")
    validate_cpp_identifier("_valid_1")
    with raises(ValueError, match=r"valid C\+\+ identifier"):
        validate_cpp_identifier("1leading_digit")
    with raises(ValueError, match=r"valid C\+\+ identifier"):
        validate_cpp_identifier("has space")


def test_validate_cpp_identifier_with_prefix_allows_leading_digit():
    # the rendered identifier (prefix + value) starts with a letter
    validate_cpp_identifier("123abc", prefix="species_")
    with raises(ValueError, match="prefixed"):
        validate_cpp_identifier("has space", prefix="species_")


def test_positive():
    positive(1)
    positive(1.0)
    with raises(ValueError, match="must be greater than 0"):
        positive(0)
    with raises(ValueError, match="must be greater than 0"):
        positive(-1.5)


def test_all_positive():
    all_positive((1, 2, 3))
    with raises(ValueError, match="must be greater than 0"):
        all_positive((1, 0, 3))
    with raises(ValueError, match="n_points"):
        all_positive((0, 2, 2), field="n_points")


def test_non_negative():
    non_negative(0)
    non_negative(3.0)
    with raises(ValueError, match="greater than or equal to 0"):
        non_negative(-0.1)


def test_less_than():
    less_than(1.0, 2.0, lesser_field="min", greater_field="max")
    with raises(ValueError, match="min must be smaller than max"):
        less_than(2.0, 2.0, lesser_field="min", greater_field="max")
    with raises(ValueError):
        less_than(3.0, 1.0, lesser_field="min", greater_field="max")


def test_component_vector_accepts_all_forms():
    assert component_vector([1, 2, 3]) == (1, 2, 3)
    assert component_vector((1, 2, 3)) == (1, 2, 3)
    assert component_vector({"x": 1, "y": 2, "z": 3}) == (1, 2, 3)


def test_component_vector_raises_actionable_error():
    with raises(ValueError, match="direction"):
        component_vector([1, 2], field="direction")
    with raises(ValueError, match="direction"):
        component_vector("nope", field="direction")


def test_unit_vector():
    unit_vector((0.0, 1.0, 0.0))
    unit_vector((1.0 / 3**0.5, 1.0 / 3**0.5, 1.0 / 3**0.5))
    with raises(ValueError, match="unit vector"):
        unit_vector((2.0, 0.0, 0.0))
    with raises(ValueError, match="infs or nans"):
        unit_vector((float("nan"), 0.0, 0.0))


def test_in_unit_interval():
    in_unit_interval((0.0, 0.5, 0.999))
    with raises(ValueError, match="\\[0, 1\\)"):
        in_unit_interval((-0.1, 0.5, 0.0))
    with raises(ValueError, match="in_cell_offset"):
        in_unit_interval((1.0, 0.5, 0.0), field="in_cell_offset")


def test_as_list():
    assert as_list(5, int) == [5]
    assert as_list([1, 2, 3], int) == [1, 2, 3]
    assert as_list("x", int) == "x"


def test_exactly_one():
    exactly_one({"a": False, "b": True})
    with raises(ValueError, match="Exactly one"):
        exactly_one({"a": False, "b": False})
    with raises(ValueError, match="Exactly one"):
        exactly_one({"a": True, "b": True})


def test_same_length():
    same_length([1, 2], [3, 4], a_field="a", b_field="b")
    with raises(ValueError, match="a and b must have the same length"):
        same_length([1, 2], [3], a_field="a", b_field="b")


def test_at_least_one_of():
    at_least_one_of({"a": True, "b": False})
    with raises(ValueError, match="At least one of"):
        at_least_one_of({"a": False, "b": False})
    with raises(ValueError, match="custom message"):
        at_least_one_of({"a": False}, message="custom message")


def test_radius_larger_than():
    radius_larger_than(2.0, 1.0)
    radius_larger_than(1.0, 1.0)
    with raises(ValueError, match="radius_si must be >= 1.0"):
        radius_larger_than(0.5, 1.0)
