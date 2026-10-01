"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+

Shared machinery for sympy-backed field functors.

Both :class:`~picongpu.picmi.distribution.AnalyticDistribution.AnalyticDistribution`
and :class:`~picongpu.picmi.applied_field.AnalyticAppliedField` describe a
physical quantity as a sympy expression of a few free variables, optionally with
named parameters supplied as additional keyword arguments. The generated C++
functors evaluate those expressions on device, so the same rules apply to both:

* the free variables must be exactly the supported coordinates/time,
* parameters must not collide with generated C++ identifiers or keywords,
* the expressions are rendered to PMAcc C++ with the :class:`PMAccPrinter`.

This module holds those shared rules so that the two features stay aligned; the
individual classes only describe *which* quantities they expose.
"""

import inspect
import re
from collections.abc import Callable, Iterable, Mapping

import sympy

from picongpu.pypicongpu.rendering.pmaccprinter import PMAccPrinter

_RENDERER = PMAccPrinter()

_RENDERED_CODE_MARKER = re.compile(r"pmacc::|::")

#: Identifiers that are always live inside the generated C++ functors. A
#: user-defined parameter must not shadow one of these.
GENERATED_IDENTIFIERS = frozenset(
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


def render(value) -> str:
    """
    Render a sympy expression, a number or an already-rendered C++ string.

    ``None`` denotes a zero component. Plain strings are parsed by sympy, while
    strings that already carry rendered PMAcc code (detected by a ``::``) are
    passed through verbatim, so a model round trip does not re-render.
    """
    if value is None:
        return "0"
    if isinstance(value, str) and _RENDERED_CODE_MARKER.search(value):
        return value
    return _RENDERER.doprint(value)


def sympify_expression(expression) -> sympy.Expr:
    """
    Parse a PICMI expression string.

    Mirrors the PICMI-standard normalisation (newlines are removed) and coerces
    non-string inputs to their string form, so a bare number becomes a constant
    expression.
    """
    return sympy.sympify(f"{expression}".replace("\n", ""))


def expression_from_callable(
    function: Callable,
    variables: Mapping[str, sympy.Symbol],
    parameters: Mapping[str, float] | None = None,
) -> sympy.Expr:
    """
    Evaluate a user-supplied callable on the coordinate symbols.

    The callable is called with the free variables (in the order given by
    ``variables``) and must return something sympy can understand. Additional
    named parameters are passed as keyword arguments when the callable accepts
    them (the same additional-kwargs mechanism as for expression strings).
    """
    # Named parameters are passed as sympy symbols (not their numeric values) so
    # that the resulting expression stays symbolic and the values are rendered
    # as compile-time constants by pypicongpu, exactly like ``*_expression``
    # strings with additional keyword arguments. We only pass the parameters
    # the callable actually asks for, so a function that only uses some
    # coordinates keeps working when unrelated parameters are present.
    accepted = _accepted_parameters(function)
    names = list(parameters or {})
    arguments = dict(variables)
    for name in names:
        if accepted is None or name in accepted:
            arguments[name] = sympy.Symbol(name)
    try:
        return sympy.sympify(function(**arguments))
    except TypeError:
        # Fall back to the AnalyticDistribution idiom: all quantities passed
        # positionally, coordinates first, then the named parameters.
        positional = list(variables.values()) + [sympy.Symbol(name) for name in names]
        return sympy.sympify(function(*positional))


def _accepted_parameters(function: Callable) -> set[str] | None:
    """
    Names the callable accepts as keyword arguments, or ``None`` for ``**kwargs``.

    Returns ``None`` when the callable accepts arbitrary keyword arguments, in
    which case every parameter may be passed. Returns an empty set when the
    signature cannot be inspected (e.g. some C callables).
    """
    try:
        signature = inspect.signature(function)
    except (TypeError, ValueError):
        return set()
    parameters = signature.parameters.values()
    if any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in parameters):
        return None
    return {
        name
        for name, parameter in signature.parameters.items()
        if parameter.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
    }


def check_parameter_names(names: Iterable[str]) -> None:
    """Reject parameter names that shadow generated C++ identifiers or keywords."""
    for name in names:
        if name in GENERATED_IDENTIFIERS:
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


def check_allowed_symbols(expressions: Mapping[str, sympy.Expr], allowed: set[str], context: str) -> None:
    """
    Reject expressions that reference symbols we cannot resolve.

    The generated C++ functors only define the supported free variables plus the
    user-defined parameters, so any other symbol would be rendered as undefined
    C++ and only fail (cryptically) at device-compile time. Fail in Python.
    """
    undefined: set[str] = set()
    for expression in expressions.values():
        undefined |= {str(symbol) for symbol in sympy.sympify(expression).free_symbols} - allowed
    if undefined:
        raise ValueError(
            f"{context} expression(s) reference undefined symbol(s) {sorted(undefined)}; the "
            "generated C++ functors only know the position (x/y/z), the time (t) and the "
            "parameters passed as additional keyword arguments."
        )



