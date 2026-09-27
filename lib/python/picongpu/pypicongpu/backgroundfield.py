"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, Field

from .rendering.pmaccprinter import PMAccPrinter


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
    return PMAccPrinter().doprint(value)


class _Parameter(BaseModel):
    """A named parameter used inside a field expression."""

    name: str
    """name of the parameter as used inside the expressions"""
    value: float
    """value assigned to the parameter (SI units)"""


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
    The design deliberately mirrors the PICMI applied-field surface so that
    the broader "field background" scopes (field arithmetic, ``as_initial``,
    ``as_injected``) can be added on top without reworking this model.
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
