"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

from copy import deepcopy

from moosetash import MissingVariable, missing_variable_raise, render
from picongpu._rendering_context import normalize_none
from pytest import raises


def test_replaces_none_recursively():
    context = {
        "top": None,
        "nested": {"inner": None, "list": [None, {"deep": None}]},
        "sequence": (None, 1, [None]),
        "untouched": "value",
    }

    result = normalize_none(context)

    assert result == {
        "top": "",
        "nested": {"inner": "", "list": ["", {"deep": ""}]},
        "sequence": ("", 1, [""]),
        "untouched": "value",
    }
    assert isinstance(result["sequence"], tuple)
    assert isinstance(result["nested"]["list"], list)


def test_does_not_mutate_input():
    context = {"top": None, "nested": {"inner": None}, "sequence": (None,)}
    snapshot = deepcopy(context)

    normalize_none(context)

    assert context == snapshot
    assert context["top"] is None
    assert context["nested"]["inner"] is None
    assert context["sequence"][0] is None


def test_preserves_false_zero_and_empty_containers():
    context = {
        "false": False,
        "zero": 0,
        "empty_string": "",
        "empty_list": [],
        "empty_tuple": (),
        "empty_dict": {},
    }

    result = normalize_none(context)

    assert result == context
    assert result["false"] is False
    assert result["zero"] == 0
    assert isinstance(result["empty_tuple"], tuple)


def test_present_none_renders_empty_under_raising_handler():
    context = normalize_none({"present": None})

    rendered = render(
        template="{{present}}",
        context=context,
        missing_variable_handler=missing_variable_raise,
    )

    assert rendered == ""


def test_absent_key_still_raises_under_raising_handler():
    context = normalize_none({"present": None})

    with raises(MissingVariable):
        render(
            template="{{absent}}",
            context=context,
            missing_variable_handler=missing_variable_raise,
        )
