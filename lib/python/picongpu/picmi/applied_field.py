"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

import sympy
from picmistandard import PICMI_AnalyticAppliedField, PICMI_ConstantAppliedField

from picongpu.pypicongpu.backgroundfield import BackgroundField

_ANALYTIC_FREE_VARIABLES = frozenset({"x", "y", "z", "t"})


def _check_only_full_domain(applied_field) -> None:
    """
    Reject region-restricted applied fields for now.

    The C++ field-background path currently renders the functor over the whole
    simulation domain. Support for PICMI ``lower_bound``/``upper_bound``
    regions is planned, but not yet implemented, so fail loudly instead of
    silently applying the field everywhere.
    """
    for bound in (applied_field.lower_bound, applied_field.upper_bound):
        if any(component is not None for component in (bound or [])):
            raise NotImplementedError(
                "PIConGPU background fields are currently only supported over the whole "
                f"simulation domain, but {type(applied_field).__name__} got {bound=} with "
                "non-None entries. Region restriction via lower_bound/upper_bound is not "
                "implemented yet."
            )


def _check_expression_symbols(applied_field, user_defined_kw) -> None:
    """
    Reject expressions that reference symbols we cannot resolve.

    The generated C++ functors only define the free variables ``x``/``y``/``z``
    (position in m) and ``t`` (time in s) plus the user-defined parameters, so
    any other symbol would be rendered as undefined C++ and only fail
    (cryptically) at device-compile time. Fail in Python instead.
    """
    allowed = _ANALYTIC_FREE_VARIABLES | {parameter["name"] for parameter in user_defined_kw}
    undefined: set[str] = set()
    for component in (
        "Ex_expression",
        "Ey_expression",
        "Ez_expression",
        "Bx_expression",
        "By_expression",
        "Bz_expression",
    ):
        expression = getattr(applied_field, component)
        if expression is None:
            continue
        undefined |= {str(symbol) for symbol in sympy.sympify(expression).free_symbols} - allowed
    if undefined:
        raise ValueError(
            "AnalyticAppliedField expression(s) reference undefined symbol(s) "
            f"{sorted(undefined)}; the generated C++ functors only know the position (x/y/z), "
            "the time (t) and the parameters passed as additional keyword arguments."
        )


class ConstantAppliedField(PICMI_ConstantAppliedField):
    """
    PIConGPU implementation of the PICMI ``ConstantAppliedField``.

    A constant field is added to the grid E and B fields around the particle
    push: particles feel it, but the field solver does not evolve it (see the
    C++ ``fieldBackground.param`` + ``FieldBackground.hpp``).

    Only whole-domain fields are supported so far, so ``lower_bound`` and
    ``upper_bound`` must be left as their default (all ``None``).

    The standard PICMI attribute names (``Ex``, ``Ey``, ``Ez`` in V/m and
    ``Bx``, ``By``, ``Bz`` in T) are used verbatim.
    """

    def get_as_pypicongpu(self) -> BackgroundField:
        _check_only_full_domain(self)
        return BackgroundField(
            ex=self.Ex,
            ey=self.Ey,
            ez=self.Ez,
            bx=self.Bx,
            by=self.By,
            bz=self.Bz,
        )


class AnalyticAppliedField(PICMI_AnalyticAppliedField):
    """
    PIConGPU implementation of the PICMI ``AnalyticAppliedField``.

    An analytic field is added to the grid E and B fields around the particle
    push: particles feel it, but the field solver does not evolve it (see the
    C++ ``fieldBackground.param`` + ``FieldBackground.hpp``).

    The expressions use the variables ``x``, ``y``, ``z`` (position in m) and
    ``t`` (time in s) and may reference user-defined parameters given as
    additional keyword arguments (as in the PICMI standard). ``Ex_expression``
    etc. are in V/m and ``Bx_expression`` etc. in T.

    Only whole-domain fields are supported so far, so ``lower_bound`` and
    ``upper_bound`` must be left as their default (all ``None``).
    """

    def get_as_pypicongpu(self) -> BackgroundField:
        _check_only_full_domain(self)
        user_defined_kw = [{"name": name, "value": value} for name, value in sorted(self.user_defined_kw.items())]
        _check_expression_symbols(self, user_defined_kw)
        return BackgroundField(
            ex=self.Ex_expression,
            ey=self.Ey_expression,
            ez=self.Ez_expression,
            bx=self.Bx_expression,
            by=self.By_expression,
            bz=self.Bz_expression,
            user_defined_kw=user_defined_kw,
        )


AnyAppliedField = ConstantAppliedField | AnalyticAppliedField

__all__ = ["AnalyticAppliedField", "AnyAppliedField", "ConstantAppliedField"]
