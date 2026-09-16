"""
This file is part of PIConGPU.
Copyright 2021-2025 PIConGPU contributors
Authors: Hannes Troepgen, Brian Edward Marre, Julian Lenz
License: GPLv3+
"""

import logging
import re
import traceback
from collections.abc import Callable

import numpy as np
from picmistandard import PICMI_AnalyticDistribution
from pydantic import ConfigDict, PrivateAttr, model_validator
from sympy import Expr, Symbol, lambdify, symbols, sympify

from picongpu.pypicongpu import species
from picongpu.pypicongpu.util import decorating_class, unsupported

"""
note on rms_velocity:
---------------------
The rms_velocity is converted to a temperature in keV. This conversion requires the mass of the species to be known,
which is not the case inside the picmi density distribution.

As an abstraction, **every** PICMI density distribution implements `picongpu_get_rms_velocity_si()` which returns a
tuple (float, float, float) with the rms_velocity per axis in SI units (m/s).

In case the density profile does not have an rms_velocity, this method **MUST** return (0, 0, 0), which is translated to
"no temperature initialization" by the owning species.

note on drift:
--------------
The drift ("velocity") is represented using either directed_velocity or centroid_velocity (v, gamma*v respectively) and
for the pypicongpu representation stored in a separate object (Drift).

To accommodate that, this separate Drift object can be requested by the method get_picongpu_drift(). In case of no drift,
this method returns None.
"""


@decorating_class("density_function", keyword_construction=True)
class AnalyticDistribution(PICMI_AnalyticDistribution):
    """
    This class represents a plasma with a density defined by an analytic expression.

    It implements the standard ``PICMI_AnalyticDistribution`` interface (``density_expression``,
    ``momentum_expressions``, ``momentum_spread_expressions``, ``lower_bound``/``upper_bound``,
    ``rms_velocity``, ``directed_velocity``, ``fill_in`` and the automatic ``user_defined_kw``
    parameter substitution).

    PIConGPU-specific extension: in addition to the standard ``density_expression: str`` you may
    provide a sympy based ``density_function`` callable (or the equivalent ``@AnalyticDistribution``
    decorator) instead of a string. Exactly one of ``density_function`` / ``density_expression``
    must be given.

    The standard's ``momentum_expressions`` (analytic ``gamma * velocity`` per axis [m/s]) and
    ``momentum_spread_expressions`` (Gaussian thermal spread sigma per axis [m/s]) are supported in
    their **constant** form only and are rendered to the constant pypicongpu ``Drift`` and
    ``Temperature`` operations. Position-dependent (function of ``x``/``y``/``z``) momentum and
    spread expressions are not implemented yet.

    Writing such functions (or rather writing sympy in general)
    comes with a few pitfalls but also advantages as listed below.
    Make sure that you familiarise yourself with writing sympy.

    Advantages:
    - The sympy language is closer to mathematical language than to coding
      which might make it more natural to use for some physicists.
    - You can extract the exact distribution
      that was used from the member `density_function`
      and use it any way you'd use any sympy expression.
      In particular, you can print it to various formats,
      say, LaTeX for automated inclusion in papers.
    - We can easily evaluate it from within python.
      This is what the __call__ operator does.
      However, code generation here can have some difficulties
      with advanced broadcasting for numpy variables.
      The operator implements a fallback in such cases.
      This fallback might be slightly slower on large inputs.
      Try rewriting your function, in case you experience performance problems.

    Pitfalls:
    - We don't handle vectors yet.
      But that's probably not too important for density expressions.
      Just be explicit handling multiple vector components for now.
    - Some operations might compile to suboptimal code
      concerning numerical performance and stability.
      Experts might want to inspect the generated C++ code
      and/or check the unit tests for the PMAccPrinter
      to find the precise mapping of sympy expressions
      to PMAcc code.
      Please approach us if you should stumble across this.
    - Control flow is an interesting topic in this regard.
      With respect to your three position coordinates
      (which will be sympy symbols internally),
      you must use pure sympy, e.g.,
      replacing if-conditions with sympy.Piecewise and so on.
      With respect to further parameters,
      you're free to use any python construct you want
      (if-conditions, loops, etc.).
    - sympy.Piecewise has the potentially surprising property
      that any pieces that you leave undefined are interpreted as nan.
      This implies that adding two complementary sympy.Piecewise
      renders the whole expression nan and not -- as you might expect --
      defined on the union of the defined regions.
      There are two options to circumvent this:
      Either you can define multiple sympy.Piecewise with
      (0.0, True) as the last condition which means 0 everywhere else.
      (Make sure it's the last!)
      Summing those up, works just as you'd expect.
      Alternatively, you can define only the (expression, condition) tuples
      and assemble them in a sympy.Piecewise in one go.
      That's the way chosen in the end-to-end tests.

    Parameters:
        density_function (Callable):
            A Python function that takes x, y, z coordinates (in SI units)
            and returns the density (in SI units) at that point.
            It should use sympy functionality.
            Provide exactly one of `density_function` or `density_expression`.
        density_expression (str):
            A sympy-parseable string expression of the density in terms of
            `x`, `y` and `z` (e.g. `"x*y*z"`). It is string-normalised (mirroring
            the PICMI standard) and then parsed with `sympy.sympify`, so
            non-string inputs are coerced to their string form (e.g. a bare number
            yields a constant density) rather than rejected. It is equivalent to
            the matching `density_function`.
            Provide exactly one of `density_function` or `density_expression`.
        directed_velocity (3-tuple of float):
            A collective velocity for the particle distribution, interpreted as a plain velocity.
            Mutually exclusive with ``momentum_expressions``: if either a non-zero
            ``directed_velocity`` and a non-``None`` ``momentum_expressions`` entry are both
            supplied, construction raises.
    """

    # The standard makes this required; PIConGPU additionally allows a sympy based
    # density_function, so make it optional and enforce exactly-one in a validator.
    density_expression: str | None = None
    density_function: Callable[[Symbol, Symbol, Symbol], Expr]
    _warned_about_lambdify_failure: bool = PrivateAttr(False)

    model_config = ConfigDict(
        arbitrary_types_allowed=True, populate_by_name=True, extra="forbid", validate_assignment=True
    )

    @model_validator(mode="before")
    @classmethod
    def _resolve_density(cls, data):
        if not isinstance(data, dict):
            return data
        has_function = data.get("density_function") is not None
        has_expression = data.get("density_expression") is not None
        if has_function == has_expression:
            raise ValueError("exactly one of density_function or density_expression must be provided")
        if has_expression:
            # Normalise like the PICMI standard does, then sympify into the
            # equivalent callable so the rendered density is identical.
            sx, sy, sz = symbols("x,y,z")
            parsed = sympify(f"{data['density_expression']}".replace("\n", ""))
            data["density_function"] = lambda x, y, z: parsed.subs({sx: x, sy: y, sz: z})
        cls._collect_spread_user_defined_kw(data)
        cls._reject_conflicting_drift(data)
        return data

    @classmethod
    def _reject_conflicting_drift(cls, data):
        # directed_velocity (plain velocity) and momentum_expressions (gamma * velocity) are
        # two different, mutually exclusive ways of setting a drift. A non-zero directed_velocity
        # combined with a non-None momentum expression was previously silently discarded; reject
        # the ambiguous combination so the two can't silently override each other.
        directed_velocity = data.get("directed_velocity")
        if directed_velocity is None:
            directed_velocity = (0.0, 0.0, 0.0)
        momentum_expressions = data.get("momentum_expressions")
        if momentum_expressions is None:
            momentum_expressions = [None, None, None]
        has_directed = any(float(v) != 0.0 for v in directed_velocity)
        has_momentum = any(e is not None for e in momentum_expressions)
        if has_directed and has_momentum:
            raise ValueError(
                "directed_velocity and momentum_expressions are mutually exclusive; "
                "provide exactly one of them to set the drift."
            )

    @classmethod
    def _collect_spread_user_defined_kw(cls, data):
        # The standard's collector scans only density_expression + momentum_expressions.
        # PIConGPU additionally renders momentum_spread_expressions, so constants referenced
        # *only* there must be collected here (before the standard's collector runs), or the
        # extra="forbid" config would reject them as extra inputs.
        spread_expressions = data.get("momentum_spread_expressions") or [None, None, None]
        spread_expressions = [None if e is None else f"{e}".replace("\n", "") for e in spread_expressions]
        known = set()
        for fname, finfo in cls.model_fields.items():
            known.add(fname)
            if finfo.alias:
                known.add(finfo.alias)
        user_defined_kw = dict(data.get("user_defined_kw", {}))
        for k in list(data.keys()):
            if k in known or k in user_defined_kw:
                continue
            if any(e is not None and re.search(r"\b%s\b" % re.escape(k), e) for e in spread_expressions):
                user_defined_kw[k] = data.pop(k)
        data["user_defined_kw"] = user_defined_kw

    def _constant_expression(self, field: str, expression: str) -> float:
        """
        Evaluate a constant momentum/spread expression (after substituting user_defined_kw)
        to a plain float. Position-dependent expressions (still referencing x/y/z) are
        rejected, and so are expressions whose parameters were never supplied.
        """
        x, y, z = symbols("x,y,z")
        resolved = sympify(expression).subs(self.user_defined_kw)
        if not resolved.free_symbols <= {x, y, z}:
            missing = sorted(sym.name for sym in resolved.free_symbols - {x, y, z})
            raise ValueError(f"{field} must be constant, but {expression!r} is missing a value for {missing}.")
        if resolved.free_symbols:
            unsupported(f"position-dependent {field}", expression)
        return float(resolved)

    def _constant_gamma_velocity(self) -> tuple[float, float, float] | None:
        """
        Evaluate the constant momentum_expressions (gamma * velocity per axis [m/s]) into a
        3-tuple. Any axis whose expression is None contributes zero (the directed_velocity is
        handled separately, using plain velocity semantics).

        Returns None if every resolved axis is zero (no drift).
        """
        gamma_velocity = [
            0.0 if expression is None else self._constant_expression("momentum_expressions", expression)
            for expression in self.momentum_expressions
        ]
        if np.allclose(gamma_velocity, 0.0):
            return None
        return tuple(gamma_velocity)  # type: ignore[return-value]

    def _constant_momentum_spread_si(self) -> tuple[float, float, float]:
        """
        Evaluate the constant momentum_spread_expressions (Gaussian sigma per axis [m/s]).
        Any axis whose expression is None contributes zero.
        """
        return tuple(
            0.0 if expression is None else self._constant_expression("momentum_spread_expressions", expression)
            for expression in self.momentum_spread_expressions
        )

    def get_as_pypicongpu(self, _):
        unsupported("fill in", self.fill_in)
        unsupported("lower bound", self.lower_bound, [None, None, None])
        unsupported("upper bound", self.upper_bound, [None, None, None])
        return species.operation.densityprofile.FreeFormula(density_expression=self._density_expression())

    def picongpu_get_rms_velocity_si(self) -> tuple[float, float, float]:
        rms_velocity = [float(v) for v in self.rms_velocity]
        return tuple(map(lambda r, s: max(r, s), rms_velocity, self._constant_momentum_spread_si()))

    def get_picongpu_drift(self) -> species.operation.momentum.Drift | None:
        """
        Get drift for pypicongpu
        :return: pypicongpu drift object or None
        """
        # The legacy directed_velocity is a plain velocity (from_velocity); the standard
        # momentum_expressions are gamma * velocity (from_gamma_velocity).
        if any(v != 0 for v in self.directed_velocity):
            return species.operation.momentum.Drift.from_velocity(tuple(self.directed_velocity))  # type: ignore[arg-type]
        gamma_velocity = self._constant_gamma_velocity()
        if gamma_velocity is None:
            return None
        return species.operation.momentum.Drift.from_gamma_velocity(gamma_velocity)

    def __call__(self, *args, **kwargs):
        args = tuple(np.asarray(a) for a in args)
        try:
            # This produces faster code but the code generation is not perfect.
            # There are cases where the generated code can't handle broadcasting properly.
            return lambdify(symbols("x,y,z"), self._density_expression(), "numpy")(*args, **kwargs)
        # We explicitly want this to be as broad as possible
        # because we have a second shot.
        # There should be no instances of this being dangerous during idiomatic use of this functionality.
        except Exception:
            if not self._warned_about_lambdify_failure:
                message = (
                    "Sympy did not manage to produce proper numpy code for your AnalyticDistribution. "
                    "If you run into performance problems, try to rewrite your function. "
                    "Here's the original error message:"
                )
                logging.warning(message)
                logging.warning(traceback.format_exc())
                logging.warning("Continuing operation using a slower serialised version now.")
                self._warned_about_lambdify_failure = True
        # This basically calls the original function in a big loop.
        # Slower but more reliable in some cases of difficult broadcasting.
        return np.vectorize(self._density_function())(*args, **kwargs)

    def _density_function(self) -> Callable[[Symbol, Symbol, Symbol], Expr]:
        """The density function with any user_defined_kw parameters substituted."""
        density_function = self.density_function
        if not self.user_defined_kw:
            return density_function
        return lambda x, y, z: density_function(x, y, z).subs(self.user_defined_kw)

    def _density_expression(self) -> Expr:
        x, y, z = symbols("x,y,z")
        return self._density_function()(x, y, z) + (0 * x * y * z)
