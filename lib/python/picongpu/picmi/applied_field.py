"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

import warnings
from collections.abc import Callable

import sympy
from picmistandard import PICMI_AnalyticAppliedField, PICMI_ConstantAppliedField
from pydantic import BaseModel, ConfigDict, Field, model_validator

from picongpu.pypicongpu import util
from picongpu.pypicongpu._field_functor import (
    _FieldFunctor,
    callable_parameter_names,
    check_allowed_symbols,
    check_parameter_names,
    sympify_expression,
)
from picongpu.pypicongpu.backgroundfield import BackgroundField

#: Component keys shared by the pypicongpu background field and the PICMI fields.
COMPONENTS = ("Ex", "Ey", "Ez", "Bx", "By", "Bz")

_ANALYTIC_FREE_VARIABLES = ("x", "y", "z", "t")


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
            util.unsupported("applied-field region restriction (lower_bound/upper_bound)", bound)


def _influence_kwargs(applied_field) -> dict:
    return dict(
        influence_particle_pusher=applied_field.picongpu_influence_particle_pusher,
        influences_plugins=applied_field.picongpu_influences_plugins,
        influences_dumps=applied_field.picongpu_influences_dumps,
    )


def merge_influence(applied_fields) -> dict:
    """
    Combine the influence knobs of several applied fields.

    The knobs configure the *single* C++ ``FieldBackgroundE``/``FieldBackgroundB``
    pair, so all applied fields must agree on them.
    """
    merged = None
    for applied_field in applied_fields:
        influence = _influence_kwargs(applied_field)
        if merged is None:
            merged = influence
        elif merged != influence:
            util.unsupported("applied fields with conflicting influence knobs", influence)
    return merged


def _check_expression_symbols(expressions: dict[str, sympy.Expr], parameters: list[dict]) -> None:
    allowed = set(_ANALYTIC_FREE_VARIABLES) | {parameter["name"] for parameter in parameters}
    check_allowed_symbols(expressions, allowed, "AnalyticAppliedField")


def _validate_components(expressions: dict[str, sympy.Expr], parameters: list[dict]) -> None:
    """
    Run the expression checks shared by the direct and the combined translation paths.

    Both :meth:`AnalyticAppliedField.get_as_pypicongpu` and
    :func:`combine_applied_fields` (the ``Simulation`` path) must reject undefined
    symbols and non-renderable parameter names, otherwise invalid C++ is emitted
    and only fails at device-compile time.
    """
    check_parameter_names(parameter["name"] for parameter in parameters)
    _check_expression_symbols(
        {component: expression for component, expression in expressions.items() if expression is not None},
        parameters,
    )


def combine_applied_fields(applied_fields) -> BackgroundField:
    """
    Combine several applied fields into the single pypicongpu background field.

    The C++ core evaluates a single ``FieldBackgroundE``/``FieldBackgroundB``
    functor pair, so the individual E/B contributions are summed per component
    (constants and expressions alike) and the parameters are merged.
    """
    applied_fields = list(applied_fields)
    influence = merge_influence(applied_fields)
    combined: dict[str, sympy.Expr] = {component: sympy.Integer(0) for component in COMPONENTS}
    parameters: dict[str, float] = {}
    for applied_field in applied_fields:
        _check_only_full_domain(applied_field)
        for component, expression in applied_field.get_components().items():
            if expression is not None:
                combined[component] = combined[component] + expression
        for parameter in applied_field.get_parameters():
            name, value = parameter["name"], parameter["value"]
            if name in parameters and parameters[name] != value:
                util.unsupported(f"redefining parameter {name!r} with a different value", value)
            parameters[name] = value
    parameter_list = [{"name": name, "value": value} for name, value in sorted(parameters.items())]
    _validate_components(combined, parameter_list)
    return BackgroundField(
        **{component.lower(): expression for component, expression in combined.items()},
        user_defined_kw=parameter_list,
        **influence,
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

    def get_components(self) -> dict[str, sympy.Expr | None]:
        """The constant E/B components as sympy expressions (``None`` is zero)."""
        return {
            component: None if getattr(self, component) is None else sympify_expression(getattr(self, component))
            for component in COMPONENTS
        }

    def get_parameters(self) -> list[dict]:
        return []

    def get_as_pypicongpu(self) -> BackgroundField:
        _check_only_full_domain(self)
        return BackgroundField(
            **{component.lower(): expression for component, expression in self.get_components().items()},
            **_influence_kwargs(self),
        )


class AnalyticAppliedField(_InfluenceOptions, PICMI_AnalyticAppliedField):
    """
    PIConGPU implementation of the PICMI ``AnalyticAppliedField``.

    An analytic field is added to the grid E and B fields around the particle
    push: particles feel it, but the field solver does not evolve it (see the
    C++ ``fieldBackground.param`` + ``FieldBackground.hpp``).

    The field mirrors the interface of
    :class:`~picongpu.picmi.distribution.AnalyticDistribution.AnalyticDistribution`
    (see :doc:`/python_package/selected_topics/functors`): each of the six
    components may be given either as a sympy-parseable ``<component>_expression``
    string or as a ``<component>_function`` callable of ``x``, ``y``, ``z`` and
    ``t``. Named parameters used by either form are supplied as additional
    keyword arguments and rendered as compile-time constants.

    ``Ex`` etc. are in V/m and ``Bx`` etc. in T. Only whole-domain fields are
    supported so far, so ``lower_bound`` and ``upper_bound`` must be left as
    their default (all ``None``).
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    Ex_function: Callable | None = None
    Ey_function: Callable | None = None
    Ez_function: Callable | None = None
    Bx_function: Callable | None = None
    By_function: Callable | None = None
    Bz_function: Callable | None = None

    @model_validator(mode="before")
    @classmethod
    def _collect_function_parameters(cls, data):
        """
        Fold the extra kwargs of ``*_function`` into ``user_defined_kw``.

        The PICMI-standard collector only inspects ``*_expression`` strings, so
        a parameter used solely inside a ``*_function`` would be rejected as an
        unknown input. To mirror
        :class:`~picongpu.picmi.distribution.AnalyticDistribution.AnalyticDistribution`
        (see #97), only kwargs whose names are *actually* declared as extra
        parameters of one of the given callables are registered; any other
        unknown kwarg is still rejected by ``extra="forbid"`` (so a typo does
        not silently become an unused constant).
        """
        if not isinstance(data, dict):
            return data
        functions = [
            data.get(f"{component}_function")
            for component in COMPONENTS
            if data.get(f"{component}_function") is not None
        ]
        if not functions:
            return data
        accepted: set[str] = set()
        accepts_any = False
        for function in functions:
            names = callable_parameter_names(function)
            if names is None:
                accepts_any = True
            else:
                accepted |= names
        accepted -= set(_ANALYTIC_FREE_VARIABLES)
        data = dict(data)
        known = set(cls.model_fields)
        user_defined_kw = dict(data.get("user_defined_kw") or {})
        for key in list(data):
            if key in known:
                continue
            if accepts_any or key in accepted:
                user_defined_kw[key] = data.pop(key)
        if user_defined_kw or "user_defined_kw" in data:
            data["user_defined_kw"] = user_defined_kw
        return data

    def _component_functor(self, component: str) -> _FieldFunctor | None:
        expression = getattr(self, f"{component}_expression")
        function = getattr(self, f"{component}_function")
        if expression is not None and function is not None:
            raise ValueError(
                f"AnalyticAppliedField got both {component}_expression and {component}_function; "
                "provide exactly one of them."
            )
        if expression is None and function is None:
            return None
        return _FieldFunctor(
            expression=expression,
            function=function,
            variables=_ANALYTIC_FREE_VARIABLES,
            parameters=self.user_defined_kw,
            context=f"AnalyticAppliedField {component}",
        )

    def get_components(self) -> dict[str, sympy.Expr | None]:
        components = {}
        for component in COMPONENTS:
            functor = self._component_functor(component)
            components[component] = None if functor is None else functor.expression
        return components

    def get_parameters(self) -> list[dict]:
        return [{"name": name, "value": value} for name, value in sorted(self.user_defined_kw.items())]

    def get_as_pypicongpu(self) -> BackgroundField:
        _check_only_full_domain(self)
        parameters = self.get_parameters()
        components = self.get_components()
        _validate_components(components, parameters)
        return BackgroundField(
            **{component.lower(): expression for component, expression in components.items()},
            user_defined_kw=parameters,
            **_influence_kwargs(self),
        )


AnyAppliedField = ConstantAppliedField | AnalyticAppliedField

__all__ = ["AnalyticAppliedField", "AnyAppliedField", "ConstantAppliedField"]
