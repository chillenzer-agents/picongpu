"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: opencode
License: GPLv3+

KHI growth-rate validation consuming openPMD output (openpmd-api).

This is the modernised re-expression of the validation in
lib/python/test/setups/ESKHI: instead of re-parsing the legacy
fields_energy.dat column and .param files, the simulation data (the
amplitude of the dominant magnetic field Bx over time) are read directly
from the openPMD series. The (corrected) growth-rate estimator and the
deviation checks of testsuite.Math are kept as the reference.
"""

import sys
import warnings
from pathlib import Path

import numpy as np
import openpmd_api as opmd

# testsuite is a standalone package next to the picongpu test tree
_TESTSUITE_ROOT = str(Path(__file__).resolve().parents[2])
if _TESTSUITE_ROOT not in sys.path:
    sys.path.insert(0, _TESTSUITE_ROOT)

with warnings.catch_warnings():
    # importing testsuite falls back to the template config and warns
    warnings.simplefilter("ignore")
    from testsuite.Math import deviation
    from testsuite.Math import math
    from testsuite.Math import physics


def bx_amplitude_per_iteration(series):
    """
    The dominant magnetic field amplitude per iteration: the maximum of
    |Bx| over the grid at each iteration. This is the f(t) series of the
    legacy fields_energy.dat "Bx" column.
    """
    amplitudes = []
    for key in sorted(series.iterations, key=int):
        chunk = series.iterations[key].meshes["B"]["x"].load_chunk()
        amplitudes.append(float(np.max(np.abs(chunk))))
    return np.asarray(amplitudes)


def times_omega_pe(series, density_si, gamma):
    """
    The iteration times in units of 1/omega_pe: the openPMD time
    (time * timeUnitSI, SI) scaled with the relativistic plasma frequency
    of the flow. PIConGPU writes timeUnitSI = 1.0; the factor is applied
    anyway so the check stays correct for other unit conventions
    (openpmd-api reports the standard default 1.0 when the attribute is
    absent).
    """
    keys = sorted(series.iterations, key=int)
    time_si = []
    for key in keys:
        iteration = series.iterations[key]
        time_si.append(float(iteration.time) * float(iteration.time_unit_SI))
    time_si = np.asarray(time_si)
    omega_pe = physics.plasmafrequence(density=density_si, gamma=gamma, relativistic=True)
    return time_si * omega_pe


def eskhi_growthrate_theory(gamma):
    """
    The analytic esKHI growth rate in units of omega_pe
    (setups/ESKHI/config.py::theory).
    """
    return 1.0 / ((8.0**0.5) * gamma)


def validate_eskhi_growthrate(openpmd_path, gamma, density_si, acceptance=0.2):
    """
    Compares the growth rate of the Bx amplitude in the openPMD series
    against the analytic esKHI value, with the same acceptance as
    setups/ESKHI/config.py (20%).

    Return:
    -------
    dict with theory, simulation growth rate, deviation, and the
    pass/fail verdict
    """
    series = opmd.Series(str(openpmd_path), opmd.Access.read_only)
    try:
        amplitude = bx_amplitude_per_iteration(series)
        time = times_omega_pe(series, density_si, gamma)
    finally:
        series.close()

    gamma_sim = math.growthRate(amplitude, time)
    theory = eskhi_growthrate_theory(gamma)

    return {
        "theory": theory,
        "simulation": gamma_sim,
        "max_diff": float(deviation.getMinDifference(theory, gamma_sim)),
        "difference_in_percentage": float(deviation.getDifferenceInPercentage(theory, gamma_sim)),
        "result": bool(deviation.getTestResult(theory, gamma_sim, acceptance)),
    }
