"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

from unittest import TestCase

import pytest
import sympy
from picongpu.picmi._FieldFunctor import _FieldFunctor


class TestFieldFunctor(TestCase):
    def test_expression_rendered_via_pmaccprinter(self):
        functor = _FieldFunctor(expression="sin(x)*cos(t)", variables=("x", "y", "z", "t"))
        assert "pmacc::math::sin(x)" in functor.render()
        assert "pmacc::math::cos(t)" in functor.render()

    def test_neither_expression_nor_function_rejected(self):
        with pytest.raises(ValueError, match="must provide"):
            _FieldFunctor()

    def test_backs_all_three_spellings(self):
        # the class translates between expression, function and sympy
        x, y, z, t = sympy.symbols("x y z t")
        functor = _FieldFunctor(function=lambda x, y, z, t: sympy.sin(x) + t, variables=("x", "y", "z", "t"))
        assert functor.symbolic == sympy.sin(x) + t
        assert functor.sympy == sympy.sin(x) + t
        assert functor.function(x, y, z, t) == sympy.sin(x) + t
        assert sympy.sympify(functor.expression) == sympy.sin(x) + t

    def test_expression_and_function_must_agree(self):
        with pytest.raises(ValueError, match="disagree"):
            _FieldFunctor(expression="x", function=lambda x, y, z, t: 2 * x, variables=("x", "y", "z", "t"))
        # equal spellings are accepted
        functor = _FieldFunctor(
            expression="x", function=lambda x, y, z, t: sympy.Symbol("x"), variables=("x", "y", "z", "t")
        )
        assert functor.symbolic == sympy.Symbol("x")

    def test_sympy_spelling_alone_is_translated(self):
        # an already-resolved sympy expression is a first-class input spelling
        x, y, z, t = sympy.symbols("x y z t")
        functor = _FieldFunctor(sympy_expression=sympy.sin(x) + t, variables=("x", "y", "z", "t"))
        assert functor.symbolic == sympy.sin(x) + t
        assert functor.sympy == sympy.sin(x) + t
        assert sympy.sympify(functor.expression) == sympy.sin(x) + t

    def test_sympy_spelling_must_agree_with_expression(self):
        x, y, z, t = sympy.symbols("x y z t")
        functor = _FieldFunctor(expression="x", sympy_expression=sympy.Symbol("x"), variables=("x", "y", "z", "t"))
        assert functor.symbolic == sympy.Symbol("x")
        with pytest.raises(ValueError, match="disagree"):
            _FieldFunctor(expression="x", sympy_expression=2 * x, variables=("x", "y", "z", "t"))

    def test_evaluate_returns_numeric_values(self):
        import numpy as np

        functor = _FieldFunctor(expression="2*x + t", variables=("x", "y", "z", "t"))
        assert functor.evaluate(3.0, 0.0, 0.0, 1.0) == 7.0
        values = functor.evaluate(np.array([0.0, 1.0, 2.0]), 0.0, 0.0, 0.0)
        np.testing.assert_allclose(values, [0.0, 2.0, 4.0])

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
        functor = _FieldFunctor(expression="float*x", variables=("x", "y", "z", "t"), parameters={"float": 2.0})
        assert functor.render() == "float_*x"
        assert functor.parameter_list() == [{"name": "float_", "value": 2.0}]

    def test_variables_can_be_position_only(self):
        # the density / per-axis momentum functors of #97 use only x, y, z
        functor = _FieldFunctor(expression="x*y*z", variables=("x", "y", "z"))
        assert functor.render() == "x*y*z"

    def test_time_not_a_free_symbol_when_not_a_variable(self):
        with pytest.raises(ValueError, match="t"):
            _FieldFunctor(expression="x*t", variables=("x", "y", "z"))

    def test_parameters_are_substituted_in_the_public_sympy_view(self):
        functor = _FieldFunctor(expression="E0*x", variables=("x", "y", "z", "t"), parameters={"E0": 3.0})
        assert functor.symbolic == sympy.Symbol("E0") * sympy.Symbol("x")
        assert functor.sympy == 3.0 * sympy.Symbol("x")
        assert functor.function(sympy.Symbol("x"), 0, 0, 0) == 3.0 * sympy.Symbol("x")
