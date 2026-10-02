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
* parameters must not shadow a live identifier of the generated functor,
* the expressions (and the parameter names) are rendered to PMAcc C++ with the
  :class:`PMAccPrinter`; that printer is the single source of truth for how an
  identifier is spelled (including escaping C++ keywords).

:class:`_FieldFunctor` packages one such expression together with its named
parameters so that the individual PICMI classes only describe *which* quantities
they expose and which coordinates those use.
"""

import inspect
import re
from collections.abc import Callable, Iterable, Mapping

import sympy

from picongpu.pypicongpu.rendering.pmaccprinter import PMAccPrinter

_RENDERER = PMAccPrinter()

_RENDERED_CODE_MARKER = re.compile(r"pmacc::|::")

#: Identifiers that are always live inside the generated C++ functors. A
#: user-defined parameter must not shadow one of these: unlike a C++ keyword
#: (which the ``PMAccPrinter`` escapes), this would silently bind a different
#: quantity inside the generated expression.
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


def render_identifier(name: str) -> str:
    """
    Render a single identifier through the PMAccPrinter.

    The printer escapes language keywords (e.g. ``float`` -> ``float_``) using
    its own reserved-word data, so user-provided parameter names cannot silently
    emit invalid C++. The same function is used for the parameter declaration in
    the generated functor, keeping the declaration and the expression in sync.
    """
    return _RENDERER.doprint(sympy.Symbol(name))


def sympify_expression(expression) -> sympy.Expr:
    """
    Parse a PICMI expression string.

    Mirrors the PICMI-standard normalisation (newlines are removed) and coerces
    non-string inputs to their string form, so a bare number becomes a constant
    expression.
    """
    return sympy.sympify(f"{expression}".replace("\n", ""))


def expression_string(expression) -> str:
    """
    The canonical PICMI string spelling of a sympy expression.

    This is the inverse of :func:`sympify_expression`, used when a model must
    expose the ``*_expression`` string field for an expression that was actually
    supplied as a callable: string-normalised (newlines removed) and stable
    across a sympify round trip.
    """
    return sympy.sstr(sympy.sympify(expression), order="none").replace("\n", "")


def function_from_expression(expression, variables: Iterable[str] = ("x", "y", "z")) -> Callable:
    """
    The callable spelling of a sympy expression.

    The returned function takes the coordinate variables (in the order of
    ``variables``) and substitutes them into the expression, so it is the
    callable counterpart of a ``*_expression`` string.
    """
    variables = tuple(variables)
    symbols = tuple(sympy.Symbol(name) for name in variables)
    resolved = sympy.sympify(expression)
    return lambda *args: resolved.subs(dict(zip(symbols, args)))


def callable_extra_parameters(function: Callable, variables: Iterable[str] = ("x", "y", "z")) -> set[str]:
    """
    Names a callable accepts beyond the coordinate variables.

    A plain ``f(x, y, z)`` yields the empty set and ``f(x, y, z, a, b)`` yields
    ``{"a", "b"}``. Only explicitly named parameters (positional-or-keyword and
    keyword-only) are reported; a catch-all ``**kwargs`` is ignored, so the
    caller cannot silently bind an arbitrary keyword to it. Returns an empty set
    when the signature cannot be inspected.
    """
    try:
        signature = inspect.signature(function)
    except (TypeError, ValueError):
        return set()
    named = (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
    return {
        name
        for name, parameter in signature.parameters.items()
        if name not in set(variables) and parameter.kind in named
    }


def expression_parameter_names(expression, variables: Iterable[str] = ("x", "y", "z")) -> set[str]:
    """
    The free-symbol names of an expression beyond the coordinate variables.

    Used to collect additional keyword arguments referenced in an expression
    string (PICMI ``user_defined_kw``). Returns an empty set for an expression
    that cannot be parsed, so the caller leaves the parse error to
    :class:`_FieldFunctor`.
    """
    try:
        free = sympify_expression(expression).free_symbols
    except Exception:
        return set()
    return {str(symbol) for symbol in free} - set(variables)


def expression_from_callable(
    function: Callable,
    variables: Mapping[str, sympy.Symbol],
    parameters: Mapping[str, float] | None = None,
) -> sympy.Expr:
    """
    Evaluate a user-supplied callable on the coordinate symbols.

    The callable is called with the free variables (in the order given by
    ``variables``) and must return something sympy can understand. Additional
    named parameters are passed as keyword arguments to the parameters the
    callable actually asks for (the same additional-kwargs mechanism as for
    expression strings).
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

    # Prefer calling by keyword, but only for signatures that actually accept it.
    # Falling back to positional arguments is reserved for a genuine
    # signature/arity mismatch: a ``TypeError`` raised *inside* the user callable
    # must propagate, not be masked by a second (positional) call.
    try:
        signature = inspect.signature(function)
    except (TypeError, ValueError):
        signature = None
    if signature is not None:
        try:
            signature.bind(**arguments)
        except TypeError:
            positional = list(variables.values()) + [sympy.Symbol(name) for name in names]
            signature.bind(*positional)
            return sympy.sympify(function(*positional))
        return sympy.sympify(function(**arguments))

    # No inspectable signature (e.g. some C callables): keep the previous
    # best-effort fallback.
    try:
        return sympy.sympify(function(**arguments))
    except TypeError:
        positional = list(variables.values()) + [sympy.Symbol(name) for name in names]
        return sympy.sympify(function(*positional))


def callable_parameter_names(function: Callable) -> set[str] | None:
    """
    Names the callable accepts beyond the coordinate/time variables.

    Returns ``None`` for a callable with ``**kwargs`` (any keyword may be a
    parameter), an empty set when the signature cannot be inspected.
    """
    accepted = _accepted_parameters(function)
    if accepted is None:
        return None
    return accepted


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
    """
    Reject parameter names that would shadow a live generated identifier.

    C++ keywords are *not* checked here: the :class:`PMAccPrinter` escapes them
    when rendering, so a parameter named ``float`` simply becomes ``float_`` in
    the generated code (both in the declaration and in the expression).
    """
    for name in names:
        if name in GENERATED_IDENTIFIERS:
            raise ValueError(
                f"Parameter name {name!r} collides with a coordinate/time variable or a generated "
                "identifier in the C++ field functors (x, y, z, t, cellIdx, currentStep, "
                "m_unitField, sim); choose a different name."
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


class _FieldFunctor:
    """
    One sympy-backed field expression plus its named parameters.

    This is the reusable core shared by every field that is rendered into a
    generated C++ functor (the six applied-field components here, the density
    and the per-axis momentum/spread fields of
    :class:`~picongpu.picmi.distribution.AnalyticDistribution.AnalyticDistribution`
    in a follow-up). It encapsulates the full pipeline once, so no caller has to
    reproduce it:

    1. resolve exactly one of an expression (a PICMI string, a plain number or a
       sympy expression) or a callable of the coordinate variables,
    2. normalise it to a sympy expression,
    3. collect/validate the named parameters supplied as additional keyword
       arguments and reject undefined free symbols,
    4. render the expression through the :class:`PMAccPrinter`.

    Parameters
    ----------
    expression:
        A PICMI expression string, a plain number or an already-parsed sympy
        expression. Mutually exclusive with ``function``.
    function:
        A callable of the coordinate variables (in the order of ``variables``)
        returning something sympy can understand. Extra named parameters are
        taken from ``parameters``. Mutually exclusive with ``expression``.
    variables:
        The names of the supported free variables, in argument order. The
        applied fields use ``("x", "y", "z", "t")``; the density and per-axis
        momentum/spread fields use ``("x", "y", "z")``.
    parameters:
        Mapping of parameter name to value (the PICMI ``user_defined_kw``).
        Values stay symbolic; they are rendered as compile-time constants.
    context:
        Prefix used in error messages (e.g. ``"AnalyticAppliedField Ex"``).

    The resolved sympy expression is available as :attr:`expression`; call
    :meth:`render` for the PMAcc C++ string and :meth:`parameter_list` for the
    validated parameters in the ``{"name": ..., "value": ...}`` form used by the
    pypicongpu models.
    """

    def __init__(
        self,
        *,
        expression=None,
        function: Callable | None = None,
        variables: Iterable[str] = ("x", "y", "z", "t"),
        parameters: Mapping[str, float] | None = None,
        context: str = "field functor",
    ):
        if (expression is None) == (function is None):
            raise ValueError(f"{context} must provide exactly one of an expression or a function.")

        self.context = context
        self.variables = tuple(variables)
        self.parameters = dict(parameters or {})
        self._symbols = {name: sympy.Symbol(name) for name in self.variables}

        if function is not None:
            self.expression = expression_from_callable(function, self._symbols, self.parameters)
        elif isinstance(expression, sympy.Expr):
            self.expression = expression
        else:
            self.expression = sympify_expression(expression)

        check_parameter_names(self.parameters)
        self._check_symbols()

    def _check_symbols(self) -> None:
        allowed = set(self.variables) | set(self.parameters)
        check_allowed_symbols({"expression": self.expression}, allowed, self.context)

    def render(self) -> str:
        """The PMAcc C++ rendering of the resolved expression."""
        return render(self.expression)

    def parameter_list(self) -> list[dict]:
        """
        The named parameters as ``{"name": ..., "value": ...}`` dicts, sorted by name.

        The name is rendered through the :class:`PMAccPrinter`, so it is the
        spelling that actually appears in the generated functor (escaped
        keywords included). Re-rendering it is idempotent, so passing it through
        the pypicongpu model validators a second time is safe.
        """
        return [{"name": render_identifier(name), "value": value} for name, value in sorted(self.parameters.items())]
