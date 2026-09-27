"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

import re
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, Field, model_validator

from .rendering.pmaccprinter import PMAccPrinter

_RENDERED_CODE_MARKER = re.compile(r"pmacc::|::")


def _render_field_expression(value) -> str:
    """
    Render a user-provided field expression (SI units, V/m or T) to C++ code.

    Accepts either ``None`` (meaning a zero field component) or a string/
    number that sympy understands. The rendered code is valid C++ and uses
    ``x``, ``y``, ``z`` (m) and ``t`` (s) as the free variables, matching the
    variables defined inside the generated ``fieldBackground.param`` functors.
    """
    if value is None:
        return "0"
    if isinstance(value, str) and _RENDERED_CODE_MARKER.search(value):
        # already-rendered C++ (e.g. fed back in from a model_dump / JSON round
        # trip): keep the rendered code verbatim rather than re-rendering it
        return value
    return PMAccPrinter().doprint(value)


class _Parameter(BaseModel):
    """A named parameter used inside a field expression."""

    name: str
    """name of the parameter as used inside the expressions"""
    value: float
    """value assigned to the parameter (SI units)"""


_CPP_KEYWORDS = frozenset(
    {
        "alignas",
        "alignof",
        "and",
        "and_eq",
        "asm",
        "auto",
        "bitand",
        "bitor",
        "bool",
        "break",
        "case",
        "catch",
        "char",
        "char8_t",
        "char16_t",
        "char32_t",
        "class",
        "compl",
        "concept",
        "const",
        "consteval",
        "constexpr",
        "constinit",
        "const_cast",
        "continue",
        "co_await",
        "co_return",
        "co_yield",
        "decltype",
        "default",
        "delete",
        "do",
        "double",
        "dynamic_cast",
        "else",
        "enum",
        "explicit",
        "export",
        "extern",
        "false",
        "float",
        "for",
        "friend",
        "goto",
        "if",
        "inline",
        "int",
        "long",
        "mutable",
        "namespace",
        "new",
        "noexcept",
        "not",
        "not_eq",
        "nullptr",
        "operator",
        "or",
        "or_eq",
        "private",
        "protected",
        "public",
        "register",
        "reinterpret_cast",
        "requires",
        "return",
        "short",
        "signed",
        "sizeof",
        "static",
        "static_assert",
        "static_cast",
        "struct",
        "switch",
        "template",
        "this",
        "thread_local",
        "throw",
        "true",
        "try",
        "typedef",
        "typeid",
        "typename",
        "union",
        "unsigned",
        "using",
        "virtual",
        "void",
        "volatile",
        "wchar_t",
        "while",
        "xor",
        "xor_eq",
    }
)

_GENERATED_IDENTIFIERS = frozenset(
    {
        # mathtools free variables + locals inside the generated functors
        "x",
        "y",
        "z",
        "t",
        "cellIdx",
        "currentStep",
        "m_unitField",
        "sim",
    }
)


class BackgroundField(BaseModel):
    """
    Background field applied to the grid E and B fields.

    The background is added to the existing field values around the particle
    push, i.e. particles feel it but the solver itself does not evolve it
    (see the C++ ``fieldBackground.param`` + ``FieldBackground.hpp``).

    The field expressions denote the SI value of the respective component
    (V/m for E, T for B) as a function of position ``x``, ``y``, ``z`` (m) and
    time ``t`` (s). Expressions are compiled to device functors via the
    PMAccPrinter, i.e. they must be expressions sympy can parse and print.

    This is the minimal, whole-domain variant of the applied-field feature.
    The design deliberately mirrors the PICMI applied-field surface. Field
    arithmetic, ``as_initial`` or ``as_injected`` map onto *separate* C++
    mechanisms (initial field assignment, incident-field planes) that would
    need their own models and templates; they are not implemented here.
    """

    type_backgroundfield: Literal[True] = True
    """discriminator for the renderer (always True)"""

    ex: Annotated[str, BeforeValidator(_render_field_expression)] = "0"
    """E_x component of the background field in V/m"""
    ey: Annotated[str, BeforeValidator(_render_field_expression)] = "0"
    """E_y component of the background field in V/m"""
    ez: Annotated[str, BeforeValidator(_render_field_expression)] = "0"
    """E_z component of the background field in V/m"""
    bx: Annotated[str, BeforeValidator(_render_field_expression)] = "0"
    """B_x component of the background field in T"""
    by: Annotated[str, BeforeValidator(_render_field_expression)] = "0"
    """B_y component of the background field in T"""
    bz: Annotated[str, BeforeValidator(_render_field_expression)] = "0"
    """B_z component of the background field in T"""

    user_defined_kw: list[_Parameter] = Field(default_factory=list)
    """
    Named parameters used inside the field expressions.

    They are rendered as compile-time constants inside the generated functors
    so that symbolic parameters of an ``AnalyticAppliedField`` resolve
    correctly (e.g. ``{"name": "wl", "value": 8.0e-7}``).
    """

    @model_validator(mode="after")
    def _check_parameter_names(self):
        for parameter in self.user_defined_kw:
            name = parameter.name
            if name in _GENERATED_IDENTIFIERS:
                raise ValueError(
                    f"Parameter name {name!r} collides with a coordinate/time variable or a generated "
                    "identifier in the C++ field functors (x, y, z, t, cellIdx, currentStep, "
                    "m_unitField, sim); choose a different name."
                )
            if name in _CPP_KEYWORDS:
                raise ValueError(
                    f"Parameter name {name!r} is a C++ keyword and cannot be used in the generated "
                    "field functors; choose a different name."
                )
        return self
