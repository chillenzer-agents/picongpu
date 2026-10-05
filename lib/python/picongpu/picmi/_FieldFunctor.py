"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+

The shared, sympy-backed field functor of the PICMI layer.

Every settable field of the analytic PICMI classes (the six applied-field
components of :class:`~picongpu.picmi.applied_field.AnalyticAppliedField`, and
the density / per-axis momentum / momentum-spread fields of
:class:`~picongpu.picmi.distribution.AnalyticDistribution.AnalyticDistribution`)
is described by the same three interchangeable spellings:

* ``<field>_function`` -- a Python callable of the coordinate variables,
* ``<field>_expression`` -- a sympy-parseable string,
* ``<field>_sympy`` -- the resolved :class:`sympy.Expr`.

:class:`_FieldFunctor` backs such a triple: it accepts any of the spellings,
validates that they agree, and translates between them. It also collects and
validates the named parameters supplied as additional keyword arguments
(``user_defined_kw``) and renders the expression to PMAcc C++.

The rendering primitives (the :class:`PMAccPrinter` wrapper, identifier
escaping and the symbol checks) live in
:mod:`picongpu.pypicongpu._field_functor` because they are shared with the
pypicongpu models; this module only adds the PICMI-level triple.
"""

import inspect
import re
from collections.abc import Callable, Iterable, Mapping

import sympy

from picongpu.pypicongpu._field_functor import (
    check_allowed_symbols,
    check_parameter_names,
    render,
    render_identifier,
    sympify_expression,
)


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


def callable_extra_parameters(function: Callable, variables: Iterable[str] = ("x", "y", "z")) -> set[str]:
    """
    Names a callable accepts beyond the coordinate variables.

    A plain ``f(x, y, z)`` yields the empty set and ``f(x, y, z, a, b)`` yields
    ``{"a", "b"}``. Only explicitly named parameters (positional-or-keyword and
    keyword-only) are reported; a catch-all ``**kwargs`` is ignored, so the
    caller cannot silently bind an arbitrary keyword to it. Returns an empty set
    when the signature cannot be inspected.
    """
    accepted = _accepted_parameters(function)
    if accepted is None:
        return set()
    return accepted - set(variables)


def expression_parameter_names(expression, variables: Iterable[str] = ("x", "y", "z")) -> set[str]:
    """
    The identifier names used by an expression beyond the coordinate variables.

    Extracted with a word-boundary scan (the same mechanism as the PICMI
    standard's parameter collector), so a name that also exists in sympy's
    namespace (e.g. ``E1``) is still recognised as a candidate parameter. The
    caller only collects the names that were actually supplied as keyword
    arguments, so unknown identifiers are left to the
    :class:`_FieldFunctor` symbol check.
    """
    identifiers = set(re.findall(r"[A-Za-z_][A-Za-z_0-9]*", f"{expression}"))
    return identifiers - set(variables)


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


def resolve(
    *,
    function: Callable | None = None,
    expression=None,
    variables: Iterable[str] = ("x", "y", "z"),
    parameters: Mapping[str, float] | None = None,
    context: str = "field functor",
) -> tuple[sympy.Expr, str, Callable]:
    """
    Translate any of the expression/function spellings into all three.

    Parameters are kept symbolic in the returned expression; the canonical
    string and callable are the exact translations of it. If both an expression
    and a function are supplied they must resolve to the same expression (a
    mismatch that still depends only on the coordinates is rejected).

    Returns ``(symbolic_expression, canonical_string, callable)``. The returned
    callable has the named parameters already substituted (it depends on the
    coordinates only), matching the public ``<field>_function`` view; the
    symbolic expression keeps them as symbols so that the pypicongpu models can
    declare the parameters separately.
    """
    variables = tuple(variables)
    symbols = {name: sympy.Symbol(name) for name in variables}
    parameters = dict(parameters or {})
    # Parse the expression with the parameter names bound to symbols, so a
    # parameter whose name also exists in sympy's namespace (e.g. ``E1``) is
    # still parsed as that symbol rather than as the sympy object.
    parameter_locals = {**symbols, **{name: sympy.Symbol(name) for name in parameters}}

    from_expression = None
    if expression is not None:
        from_expression = (
            expression if isinstance(expression, sympy.Expr) else sympify_expression(expression, parameter_locals)
        )
    from_function = None
    if function is not None:
        # The callable receives the parameters as (symbolic) keywords, exactly
        # like an expression string references them by name.
        from_function = expression_from_callable(function, symbols, parameters)

    if from_expression is not None and from_function is not None:
        # Compare the two spellings with the parameters substituted, so a
        # symbolic expression and its (numeric) callable counterpart agree.
        difference = sympy.simplify(from_expression.subs(parameters) - from_function.subs(parameters))
        if difference != 0:
            raise ValueError(
                f"{context} expression and function disagree by {difference!r}; "
                "provide one spelling, or two that agree."
            )
    if from_expression is not None:
        symbolic = from_expression
    else:
        symbolic = from_function
    return symbolic, expression_string(symbolic), function_from_expression(symbolic.subs(parameters), variables)


class _FieldFunctor:
    """
    One sympy-backed field expression plus its named parameters.

    This is the reusable core shared by every field that is rendered into a
    generated C++ functor. It encapsulates the full pipeline once, so no caller
    has to reproduce it:

    1. resolve any of the interchangeable spellings (a PICMI string, a plain
       number, an already-parsed sympy expression or a callable of the
       coordinate variables) and check that they agree,
    2. normalise to a sympy expression and translate between the string, sympy
       and callable spellings,
    3. collect/validate the named parameters supplied as additional keyword
       arguments and reject undefined free symbols,
    4. render the expression through the :class:`PMAccPrinter`.

    Parameters
    ----------
    expression:
        A PICMI expression string, a plain number or an already-parsed sympy
        expression.
    function:
        A callable of the coordinate variables (in the order of ``variables``)
        returning something sympy can understand. Extra named parameters are
        taken from ``parameters``. May be combined with ``expression`` if the
        two agree; at least one of the two must be given.
    variables:
        The names of the supported free variables, in argument order. The
        applied fields use ``("x", "y", "z", "t")``; the density and per-axis
        momentum/spread fields use ``("x", "y", "z")``.
    parameters:
        Mapping of parameter name to value (the PICMI ``user_defined_kw``).
        Values stay symbolic in :attr:`symbolic`; they are rendered as
        compile-time constants.
    context:
        Prefix used in error messages (e.g. ``"AnalyticAppliedField Ex"``).

    Attributes
    ----------
    symbolic:
        The resolved expression with parameters kept symbolic.
    sympy:
        :attr:`symbolic` with every parameter substituted by its value (the
        public ``<field>_sympy`` view).
    expression:
        The canonical PICMI string spelling (parameters symbolic).
    function:
        The callable spelling; substitutes the coordinate arguments into
        :attr:`sympy`.
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
        if expression is None and function is None:
            raise ValueError(f"{context} must provide an expression or a function.")

        self.context = context
        self.variables = tuple(variables)
        self.parameters = dict(parameters or {})
        self.symbolic, self.expression, self.function = resolve(
            expression=expression,
            function=function,
            variables=self.variables,
            parameters=self.parameters,
            context=context,
        )
        self.sympy = self.symbolic.subs(self.parameters)

        check_parameter_names(self.parameters)
        self._check_symbols()

    def _check_symbols(self) -> None:
        allowed = set(self.variables) | set(self.parameters)
        check_allowed_symbols({"expression": self.symbolic}, allowed, self.context)

    def render(self) -> str:
        """
        The PMAcc C++ rendering, with parameters kept as named symbols.

        This is the form used by the pypicongpu ``BackgroundField``, which
        declares the parameters separately (see :meth:`parameter_list`).
        """
        return render(self.symbolic)

    def parameter_list(self) -> list[dict]:
        """
        The named parameters as ``{"name": ..., "value": ...}`` dicts, sorted by name.

        The name is rendered through the :class:`PMAccPrinter`, so it is the
        spelling that actually appears in the generated functor (escaped
        keywords included). Re-rendering it is idempotent, so passing it through
        the pypicongpu model validators a second time is safe.
        """
        return [{"name": render_identifier(name), "value": value} for name, value in sorted(self.parameters.items())]
