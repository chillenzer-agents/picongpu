"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+

Predefined background (applied) field setups for the end-to-end test.

Each entry is a callable building a single applied field. Several of them are
added to one simulation so that the test also covers the summation of multiple
applied fields into the single C++ background functor pair.
"""

from sympy import cos, exp, sin

from picongpu import picmi

# A spatial-temporal scale in SI units that keeps the field smooth over the
# small test box (positions are between 0 and 64 m; see arbitrary_parameters).
WAVENUMBER = 2.0 * 3.141592653589793 / 64.0
FREQUENCY = 2.0 * 3.141592653589793 / 50.0


APPLIED_FIELDS = {
    # constant field: one E and one B component
    "constant": lambda: picmi.ConstantAppliedField(Ex=1.0e6, Bz=0.5),
    # analytic strings, including additional named parameters
    "analytic_string": lambda: picmi.AnalyticAppliedField(
        Ey_expression="E0 * sin(k * x) * cos(w * t)",
        Bx_expression="B0 * exp(-t / tau)",
        E0=2.0e6,
        B0=0.25,
        k=WAVENUMBER,
        w=FREQUENCY,
        tau=1.0e-3,
    ),
    # analytic callables, mirroring the AnalyticDistribution interface;
    # the named parameters are passed as additional keyword arguments
    "analytic_function": lambda: picmi.AnalyticAppliedField(
        Ez_function=lambda x, y, z, t, E1, k, w: E1 * sin(k * y) * cos(w * t),
        By_function=lambda x, y, z, t, B1, tau: B1 * exp(-t / tau),
        E1=1.5e6,
        B1=0.125,
        k=WAVENUMBER,
        w=FREQUENCY,
        tau=1.0e-3,
    ),
}

# The summed components ``Simulation.get_as_pypicongpu`` must produce. Keeping
# them here (rather than only in the test) documents the expected combination.
EXPECTED = {
    "ex": lambda x, y, z, t: 1.0e6,
    "ey": lambda x, y, z, t: 2.0e6 * sin(WAVENUMBER * x) * cos(FREQUENCY * t),
    "ez": lambda x, y, z, t: 1.5e6 * sin(WAVENUMBER * y) * cos(FREQUENCY * t),
    "bx": lambda x, y, z, t: 0.25 * exp(-t / 1.0e-3),
    "by": lambda x, y, z, t: 0.125 * exp(-t / 1.0e-3),
    "bz": lambda x, y, z, t: 0.5,
}
