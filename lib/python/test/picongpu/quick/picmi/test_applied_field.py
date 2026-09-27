"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

from pathlib import Path
from unittest import TestCase

import pytest
from picongpu import picmi
from picongpu.pypicongpu.backgroundfield import BackgroundField

REPO_ROOT = Path(__file__).resolve().parents[6]
STATIC_FIELDBACKGROUND_PARAM = REPO_ROOT / "include" / "picongpu" / "param" / "fieldBackground.param"


def _get_sim():
    grid = picmi.Cartesian3DGrid(
        number_of_cells=[16, 16, 16],
        lower_bound=[0, 0, 0],
        upper_bound=[16e-6, 16e-6, 16e-6],
        lower_boundary_conditions=["open", "open", "periodic"],
        upper_boundary_conditions=["open", "open", "periodic"],
    )
    solver = picmi.ElectromagneticSolver(method="Yee", grid=grid)
    return picmi.Simulation(time_step_size=1e-14, max_steps=4, solver=solver)


def _nonblank_lines(text: str):
    return [line for line in text.splitlines() if line.strip()]


class TestConstantAppliedField(TestCase):
    def test_translation(self):
        applied_field = picmi.ConstantAppliedField(Ex=1e6, By=0.5)
        background = applied_field.get_as_pypicongpu()

        assert isinstance(background, BackgroundField)
        assert background.ex == "1000000.0"
        assert background.ey == "0"
        assert background.ez == "0"
        assert background.bx == "0"
        assert background.by == "0.5"
        assert background.bz == "0"
        assert background.user_defined_kw == []

    def test_expression_rendering(self):
        background = picmi.ConstantAppliedField(Ez=2.5).get_as_pypicongpu()
        assert background.ez == "2.5"


class TestAnalyticAppliedField(TestCase):
    def test_translation_renders_expression_via_pmaccprinter(self):
        applied_field = picmi.AnalyticAppliedField(Ex_expression="sin(x)*cos(t)")
        background = applied_field.get_as_pypicongpu()

        assert isinstance(background, BackgroundField)
        assert "pmacc::math::sin(x)" in background.ex
        assert "pmacc::math::cos(t)" in background.ex
        assert background.ey == "0"
        assert background.ez == "0"

    def test_user_defined_kw(self):
        applied_field = picmi.AnalyticAppliedField(Ex_expression="b0*sin(2*pi*y/wl)", b0=1e5, wl=800e-9)
        background = applied_field.get_as_pypicongpu()

        params = {p.name: p.value for p in background.user_defined_kw}
        assert params == {"b0": 1e5, "wl": 800e-9}
        # parameters are resolved inside the rendered expression
        assert "b0" in background.ex
        assert "wl" in background.ex


class TestSimulationBackgroundField(TestCase):
    def test_no_applied_field(self):
        sim = _get_sim()
        assert sim.get_as_pypicongpu().background_field is None

    def test_single_constant_applied_field(self):
        sim = _get_sim()
        sim.add_applied_field(picmi.ConstantAppliedField(Ez=3e6))
        background = sim.get_as_pypicongpu().background_field
        assert isinstance(background, BackgroundField)
        assert background.ez == "3000000.0"

    def test_single_analytic_applied_field(self):
        sim = _get_sim()
        sim.add_applied_field(picmi.AnalyticAppliedField(Bx_expression="0.1*x/L", L=1e-3))
        background = sim.get_as_pypicongpu().background_field
        assert "x/L" in background.bx
        assert "0.1" in background.bx
        assert "L" in background.bx

    def test_multiple_applied_fields_rejected(self):
        sim = _get_sim()
        sim.add_applied_field(picmi.ConstantAppliedField(Ez=1.0))
        sim.add_applied_field(picmi.ConstantAppliedField(Bz=1.0))
        with pytest.raises(NotImplementedError):
            sim.get_as_pypicongpu()

    def test_unsupported_applied_field_type_rejected(self):
        from picmistandard import PICMI_LoadGriddedField

        sim = _get_sim()
        # Standard PICMI applied fields that map to other C++ mechanisms
        # (injection/initialization) are not supported as background fields yet.
        sim.add_applied_field(picmi.AnalyticAppliedField(Ex_expression="1.0"))
        sim.add_applied_field(PICMI_LoadGriddedField(read_fields_from_path="/tmp/dummy.h5"))
        with pytest.raises(NotImplementedError):
            sim.get_as_pypicongpu()

    def test_region_bounds_rejected(self):
        sim = _get_sim()
        sim.add_applied_field(picmi.ConstantAppliedField(Ez=1.0, lower_bound=[0, 0, 0], upper_bound=[1e-6, 1e-6, 1e-6]))
        with pytest.raises(NotImplementedError):
            sim.get_as_pypicongpu()

    def test_render_context_is_none_without_applied_field(self):
        sim = _get_sim()
        rendered = sim.get_as_pypicongpu().get_rendering_context()
        assert "background_field" in rendered
        assert rendered["background_field"] is None

    def test_render_context_contains_background_field(self):
        sim = _get_sim()
        sim.add_applied_field(picmi.ConstantAppliedField(Ey=1e6))
        context = sim.get_as_pypicongpu().get_rendering_context()
        assert context["background_field"] is not None
        for key in ("ex", "ey", "ez", "bx", "by", "bz"):
            assert key in context["background_field"]
        # the renderer only accepts the standard leaf types
        assert isinstance(context["background_field"]["ey"], str)


class TestRenderedParamFunctionallyEqual(TestCase):
    """Render an input setup and compare the generated fieldBackground.param to the static one.

    These are rendering-level checks rather than pinning of exact output, so
    they stay robust against formatting changes: the generated file must be
    build-relevant-identical when no background field is configured."""

    def _render_setup(self, applied_field=None):
        import tempfile

        sim = _get_sim()
        if applied_field is not None:
            sim.add_applied_field(applied_field)
        with tempfile.TemporaryDirectory() as tmpdir:
            sim.write_input_file(Path(tmpdir) / "setup")
            param_path = Path(tmpdir) / "setup" / "include" / "picongpu" / "param" / "fieldBackground.param"
            return param_path.read_text()

    def test_default_rendering_equivalent_to_static_param(self):
        rendered = self._render_setup()
        static = STATIC_FIELDBACKGROUND_PARAM.read_text()
        assert _nonblank_lines(rendered) == _nonblank_lines(static)

    def test_configured_rendering_enables_background(self):
        rendered = self._render_setup(picmi.ConstantAppliedField(Ey=1e6))
        assert "InfluenceParticlePusher = true" in rendered
        assert "1000000.0" in rendered
        # the J background stays off
        assert "FieldBackgroundJ" in rendered
        assert "activated = false" in rendered
