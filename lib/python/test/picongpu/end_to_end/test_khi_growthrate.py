"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: opencode
License: GPLv3+

Checks the openPMD-based KHI growth-rate validation (khi_growthrate.py).

The synthetic-series tests exercise the full pipeline (openPMD read ->
growth rate -> analytic comparison) without a real KHI run. The last
test validates the openPMD output of a real KHI run if it is provided
via the PIC_KHI_OPENPMD environment variable.
"""

import os

import numpy as np
import openpmd_api as opmd
import pytest

from .khi_growthrate import (
    bx_amplitude_per_iteration,
    eskhi_growthrate_theory,
    physics as ts_physics,
    times_omega_pe,
    validate_eskhi_growthrate,
)


@pytest.fixture(scope="module")
def _openpmd_read_roundtrip(tmp_path_factory):
    """
    Self-check of the openpmd-api read path before running the checks on
    it: write a two-iteration series and read it back.

    In some environments (e.g. unofficial openpmd-api builds for Python
    3.14) the read path returns corrupted data even though the files on
    disk are correct (verifiable with h5py); the CI matrix uses Python
    3.11-3.13, where this is expected to work.
    """
    path = tmp_path_factory.mktemp("openpmd_check") / "check.h5"
    series = opmd.Series(str(path), opmd.Access.create)
    for step in (0, 1):
        iteration = series.iterations[step]
        iteration.time = float(step)
        iteration.dt = 1.0
        component = iteration.meshes["E"]["x"]
        component.reset_dataset(opmd.Dataset(np.dtype(np.float64), [4]))
        component.store_chunk(np.full(4, float(step) + 1.0))
    series.flush()
    series.close()

    series = opmd.Series(str(path), opmd.Access.read_only)
    values = [float(series.iterations[k].meshes["E"]["x"].load_chunk()[0]) for k in (0, 1)]
    series.close()

    if values != [1.0, 2.0]:
        pytest.skip(
            "openpmd-api read path broken in this environment "
            f"(round-trip returned {values!r}, expected [1.0, 2.0])"
        )


def _write_synthetic_series(path, gamma=1.6, density_si=1.0e25, n_cells=16, steps=(0, 5, 10, 15, 20, 25)):
    """
    Writes an openPMD series whose Bx field grows exponentially with the
    analytic esKHI rate, so the validated growth rate must recover it.
    """
    omega_pe = ts_physics.plasmafrequence(density=density_si, gamma=gamma, relativistic=True)
    dt = 0.1 / omega_pe

    series = opmd.Series(str(path), opmd.Access.create)
    for step in steps:
        iteration = series.iterations[step]
        iteration.time = step * dt
        iteration.dt = dt
        amplitude = np.exp(eskhi_growthrate_theory(gamma) * step * dt * omega_pe)
        cells = (amplitude * (1.0 + 1e-3 * np.arange(n_cells))).astype(np.float64)
        component = iteration.meshes["B"]["x"]
        component.reset_dataset(opmd.Dataset(np.dtype(np.float64), [n_cells]))
        component.store_chunk(cells)
    series.flush()
    series.close()


class TestSyntheticSeries:
    def test_growth_rate_recovers_analytic_rate(self, tmp_path, _openpmd_read_roundtrip):
        gamma = 1.6
        density_si = 1.0e25
        path = tmp_path / "khi.h5"
        _write_synthetic_series(path, gamma=gamma, density_si=density_si)

        result = validate_eskhi_growthrate(path, gamma=gamma, density_si=density_si)

        np.testing.assert_allclose(result["simulation"], eskhi_growthrate_theory(gamma), rtol=1e-6)

    def test_validation_passes(self, tmp_path, _openpmd_read_roundtrip):
        gamma = 1.6
        density_si = 1.0e25
        path = tmp_path / "khi.h5"
        _write_synthetic_series(path, gamma=gamma, density_si=density_si)

        result = validate_eskhi_growthrate(path, gamma=gamma, density_si=density_si)

        assert result["result"] is True
        assert abs(result["difference_in_percentage"]) < 1.0

    def test_bx_amplitude_and_times(self, tmp_path, _openpmd_read_roundtrip):
        gamma = 1.6
        density_si = 1.0e25
        path = tmp_path / "khi.h5"
        _write_synthetic_series(path, gamma=gamma, density_si=density_si)

        series = opmd.Series(str(path), opmd.Access.read_only)
        try:
            amplitude = bx_amplitude_per_iteration(series)
            time = times_omega_pe(series, density_si, gamma)
        finally:
            series.close()

        omega_pe = ts_physics.plasmafrequence(density=density_si, gamma=gamma, relativistic=True)
        steps = np.array([0, 5, 10, 15, 20, 25])
        expected = np.exp(eskhi_growthrate_theory(gamma) * steps * 0.1) * (1.0 + 1e-3 * 15)
        np.testing.assert_allclose(amplitude, expected, rtol=1e-12)
        np.testing.assert_allclose(time, steps * 0.1, rtol=1e-12)


def test_real_khi_run_validation(_openpmd_read_roundtrip):
    openpmd_path = os.environ.get("PIC_KHI_OPENPMD")
    if not openpmd_path:
        pytest.skip("set PIC_KHI_OPENPMD to the openPMD output of a KHI run")

    # defaults from share/picongpu/tests/KHI_growthRate/include/picongpu/param
    gamma = float(os.environ.get("PIC_KHI_GAMMA", "1.021"))
    density_si = float(os.environ.get("PIC_KHI_DENSITY_SI", "1.0e25"))

    result = validate_eskhi_growthrate(openpmd_path, gamma=gamma, density_si=density_si)
    assert result["result"] is True
