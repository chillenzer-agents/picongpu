"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

from unittest import TestCase

import pytest
import sympy
from picongpu.pypicongpu._field_functor import _FieldFunctor


class TestFieldFunctor(TestCase):
    def test_expression_rendered_via_pmaccprinter(self):
        functor = _FieldFunctor(expression="sin(x)*cos(t)", variables=("x", "y", "z", "t"))
        assert "pmacc::math::sin(x)" in functor.render()
        assert "pmacc::math::cos(t)" in functor.render()

    def test_exactly_one_of_expression_and_function(self):
        # neither form
        with pytest.raises(ValueError, match="exactly one"):
            _FieldFunctor()
        # both forms
        with pytest.raises(ValueError, match="exactly one"):
            _FieldFunctor(expression="x", function=lambda x, y, z, t: x)

    def test_callable_with_extra_parameters(self):
        functor = _FieldFunctor(
            function=lambda x, y, z, t, E0, wl: E0 * sympy.sin(2 * sympy.pi * y / wl),
            variables=("x", "y", "z", "t"),
            parameters={"E0": 1.0e5, "wl": 8.0e-7},
        )
        assert functor.parameter_list() == [
            {"name": "E0", "value": 1.0e5},
            {"name": "wl", "value": 8.0e-7},
        ]
        assert "E0" in functor.render()
        assert "wl" in functor.render()

    def test_undefined_symbol_rejected(self):
        with pytest.raises(ValueError, match="wl"):
            _FieldFunctor(expression="wl*sin(x)", variables=("x", "y", "z", "t"))

    def test_parameter_colliding_with_generated_identifier_rejected(self):
        with pytest.raises(ValueError, match="collides"):
            _FieldFunctor(expression="cellIdx*x", variables=("x", "y", "z", "t"), parameters={"cellIdx": 2.0})

    def test_keyword_parameter_escaped(self):
        functor = _FieldFunctor(
            expression="float*x", variables=("x", "y", "z", "t"), parameters={"float": 2.0}
        )
        assert functor.render() == "float_*x"
        assert functor.parameter_list() == [{"name": "float_", "value": 2.0}]

    def test_variables_can_be_position_only(self):
        # the density / per-axis momentum functors in #97 use only x, y, z
        functor = _FieldFunctor(expression="x*y*z", variables=("x", "y", "z"))
        assert functor.render() == "x*y*z"

    def test_time_not_a_free_symbol_when_not_a_variable(self):
        with pytest.raises(ValueError, match="t"):
            _FieldFunctor(expression="x*t", variables=("x", "y", "z"))
