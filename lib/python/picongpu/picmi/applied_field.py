"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

import warnings

import sympy
from picmistandard import PICMI_AnalyticAppliedField, PICMI_ConstantAppliedField
from pydantic import BaseModel, Field, model_validator

from picongpu.pypicongpu.backgroundfield import BackgroundField

_ANALYTIC_FREE_VARIABLES = frozenset({"x", "y", "z", "t"})


class _InfluenceOptions(BaseModel):
    """
    PIConGPU-specific influence knobs shared by the applied-field classes.

    The PICMI standard has no notion of field-background visibility, so these
    are PIConGPU extensions. They are declared as real fields (rather than left
    to the standard ``user_defined_kw`` catch-all) so that they are not silently
    treated as expression parameters. The names carry the ``picongpu_`` prefix
    as required for code-specific PICMI inputs.
    """

    picongpu_influence_particle_pusher: bool = Field(
        default=True,
        description=(
            "Whether particles feel the background (C++ ``InfluenceParticlePusher``). "
            "With ``False`` the whole background is disabled in the core, exactly like "
            "the legacy ``fieldBackground.param``."
        ),
    )
    picongpu_influences_plugins: bool = Field(
        default=True,
        description="Whether plugins see the background (C++ ``fieldBackground.influencesPlugins``).",
    )
    picongpu_influences_dumps: bool = Field(
        default=True,
        description="Whether dumps (incl. checkpoints) include the background (C++ ``fieldBackground.influencesDumps``).",
    )

    @model_validator(mode="after")
    def _warn_on_moot_visibility_knobs(self):
        if self.picongpu_influence_particle_pusher:
            return self
        explicitly_set = {"picongpu_influences_plugins", "picongpu_influences_dumps"} & self.model_fields_set
        if explicitly_set:
            warnings.warn(
                "picongpu_influence_particle_pusher=False disables the whole background, so "
                f"{' and '.join(sorted(explicitly_set))} has no effect: nothing adds the "
                "background to the fields. The pusher knob takes precedence.",
                UserWarning,
                stacklevel=2,
            )
        return self


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


class ConstantAppliedField(_InfluenceOptions, PICMI_ConstantAppliedField):
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
            influence_particle_pusher=self.picongpu_influence_particle_pusher,
            influences_plugins=self.picongpu_influences_plugins,
            influences_dumps=self.picongpu_influences_dumps,
        )


class AnalyticAppliedField(_InfluenceOptions, PICMI_AnalyticAppliedField):
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
            influence_particle_pusher=self.picongpu_influence_particle_pusher,
            influences_plugins=self.picongpu_influences_plugins,
            influences_dumps=self.picongpu_influences_dumps,
            user_defined_kw=user_defined_kw,
        )


AnyAppliedField = ConstantAppliedField | AnalyticAppliedField

__all__ = ["AnalyticAppliedField", "AnyAppliedField", "ConstantAppliedField"]
