"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

import warnings
from pathlib import Path
from unittest import TestCase

import pytest
import sympy
from picongpu import picmi
from picongpu.pypicongpu.backgroundfield import BackgroundField
from picongpu.pypicongpu.util import UnsupportedFeatureError

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

    def test_influence_defaults(self):
        background = picmi.ConstantAppliedField(Ex=1e6).get_as_pypicongpu()
        assert background.influence_particle_pusher is True
        assert background.influences_plugins is True
        assert background.influences_dumps is True

    def test_influence_knobs_forwarded(self):
        with pytest.warns(UserWarning, match="has no effect"):
            applied_field = picmi.ConstantAppliedField(
                Ex=1e6,
                picongpu_influence_particle_pusher=False,
                picongpu_influences_plugins=False,
                picongpu_influences_dumps=True,
            )
        background = applied_field.get_as_pypicongpu()
        assert background.influence_particle_pusher is False
        assert background.influences_plugins is False
        assert background.influences_dumps is True

    def test_moot_visibility_knobs_warn_when_pusher_disabled(self):
        # pusher=False disables the whole background, so explicitly setting the
        # visibility knobs is moot and must be surfaced instead of silently ignored
        with pytest.warns(UserWarning, match="has no effect"):
            picmi.ConstantAppliedField(
                Ex=1e6,
                picongpu_influence_particle_pusher=False,
                picongpu_influences_plugins=False,
            )
        with pytest.warns(UserWarning, match="has no effect"):
            picmi.ConstantAppliedField(
                Ex=1e6,
                picongpu_influence_particle_pusher=False,
                picongpu_influences_dumps=True,
            )

    def test_no_warning_for_default_visibility_knobs(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            picmi.ConstantAppliedField(Ex=1e6, picongpu_influence_particle_pusher=False)
            picmi.ConstantAppliedField(Ex=1e6, picongpu_influences_plugins=False)


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

    def test_influence_knobs_are_not_expression_parameters(self):
        # the picongpu_* extension kwargs must be intercepted before the standard
        # base class funnels unknown kwargs into user_defined_kw
        with pytest.warns(UserWarning, match="has no effect"):
            applied_field = picmi.AnalyticAppliedField(
                Ex_expression="b0*x",
                b0=2.0,
                picongpu_influence_particle_pusher=False,
                picongpu_influences_plugins=False,
                picongpu_influences_dumps=False,
            )
        background = applied_field.get_as_pypicongpu()
        assert [p.name for p in background.user_defined_kw] == ["b0"]
        assert background.influence_particle_pusher is False
        assert background.influences_plugins is False
        assert background.influences_dumps is False

    def test_undefined_symbol_rejected(self):
        applied_field = picmi.AnalyticAppliedField(Ex_expression="wl*sin(x)")
        with pytest.raises(ValueError, match="wl"):
            applied_field.get_as_pypicongpu()

    def test_colliding_parameter_name_rejected(self):
        applied_field = picmi.AnalyticAppliedField(Ex_expression="x/L", x=2.0, L=3.0)
        with pytest.raises(ValueError, match="collides"):
            applied_field.get_as_pypicongpu()

    def test_cpp_keyword_parameter_name_rejected(self):
        applied_field = picmi.AnalyticAppliedField(Ex_expression="float*x", float=2.0)
        with pytest.raises(ValueError, match="C\\+\\+ keyword"):
            applied_field.get_as_pypicongpu()

    def test_lower_upper_bound_none_accepted(self):
        # the whole-domain case is the default (all-None bounds)
        applied_field = picmi.AnalyticAppliedField(Ex_expression="x")
        background = applied_field.get_as_pypicongpu()
        assert background.ex == "x"


class TestAnalyticAppliedFieldFunctionInterface(TestCase):
    """The AnalyticDistribution-equivalent ``*_function`` spelling for all six components."""

    CASES = [
        ("Ex", lambda x, y, z, t: sympy.sin(x)),
        ("Ey", lambda x, y, z, t: sympy.cos(y)),
        ("Ez", lambda x, y, z, t: x + y + z),
        ("Bx", lambda x, y, z, t: sympy.exp(-t)),
        ("By", lambda x, y, z, t: sympy.Abs(z)),
        ("Bz", lambda x, y, z, t: 2.0 * t),
    ]

    def test_all_components_accept_functions(self):
        for component, function in self.CASES:
            with self.subTest(component=component):
                applied_field = picmi.AnalyticAppliedField(**{f"{component}_function": function})
                background = applied_field.get_as_pypicongpu()
                assert getattr(background, component.lower()) != "0"

    def test_function_and_expression_are_equivalent(self):
        for component, function in self.CASES:
            with self.subTest(component=component):
                x, y, z, t = sympy.symbols("x y z t")
                via_function = picmi.AnalyticAppliedField(**{f"{component}_function": function}).get_as_pypicongpu()
                expected = picmi.AnalyticAppliedField(
                    **{f"{component}_expression": str(function(x, y, z, t))}
                ).get_as_pypicongpu()
                assert getattr(via_function, component.lower()) == getattr(expected, component.lower())

    def test_function_extra_kwargs_become_parameters(self):
        applied_field = picmi.AnalyticAppliedField(
            Ex_function=lambda x, y, z, t, E0, wl: E0 * sympy.sin(2 * sympy.pi * y / wl),
            E0=1.0e5,
            wl=800e-9,
        )
        background = applied_field.get_as_pypicongpu()
        params = {p.name: p.value for p in background.user_defined_kw}
        assert params == {"E0": 1.0e5, "wl": 800e-9}
        assert "E0" in background.ex
        assert "wl" in background.ex

    def test_expression_and_function_for_same_component_rejected(self):
        applied_field = picmi.AnalyticAppliedField(Ex_expression="1.0", Ex_function=lambda x, y, z, t: sympy.Integer(1))
        with pytest.raises(ValueError, match="both Ex_expression and Ex_function"):
            applied_field.get_as_pypicongpu()

    def test_function_undefined_symbol_rejected(self):
        unknown = sympy.Symbol("unknown")
        applied_field = picmi.AnalyticAppliedField(Ex_function=lambda x, y, z, t: unknown * x)
        with pytest.raises(ValueError, match="unknown"):
            applied_field.get_as_pypicongpu()

    def test_expression_only_unreferenced_kwarg_still_rejected(self):
        # the standard collector stays in charge for pure-expression inputs
        with pytest.raises(Exception, match="bogus"):
            picmi.AnalyticAppliedField(Ex_expression="x", bogus=3.0)

    def test_mixed_expression_and_function_parameters(self):
        applied_field = picmi.AnalyticAppliedField(
            Ex_expression="q*x",
            Ey_function=lambda x, y, z, t, r: r * y,
            q=1.0,
            r=2.0,
        )
        background = applied_field.get_as_pypicongpu()
        params = {p.name: p.value for p in background.user_defined_kw}
        assert params == {"q": 1.0, "r": 2.0}
        assert "q" in background.ex
        assert "r" in background.ey

    def test_unrelated_parameter_is_not_forced_into_function(self):
        # a function that does not use an expression's parameter must still work
        applied_field = picmi.AnalyticAppliedField(
            Ex_expression="q*x",
            Ey_function=lambda x, y, z, t: sympy.Integer(5),
            q=1.0,
        )
        background = applied_field.get_as_pypicongpu()
        assert background.ey == "5"


class TestBackgroundFieldRoundTrip(TestCase):
    def test_json_roundtrip_idempotent(self):
        background = picmi.AnalyticAppliedField(Ex_expression="sin(x)*cos(t)").get_as_pypicongpu()
        restored = BackgroundField.model_validate_json(background.model_dump_json())
        assert restored.ex == background.ex
        assert restored.bz == "0"
        assert restored.user_defined_kw == background.user_defined_kw


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

    def test_multiple_constant_applied_fields_are_summed(self):
        sim = _get_sim()
        sim.add_applied_field(picmi.ConstantAppliedField(Ez=1.0))
        sim.add_applied_field(picmi.ConstantAppliedField(Ez=2.0, Bz=3.0))
        background = sim.get_as_pypicongpu().background_field
        assert isinstance(background, BackgroundField)
        assert background.ez == "3.0"
        assert background.bz == "3.0"
        assert background.ex == "0"

    def test_constant_and_analytic_applied_fields_are_summed(self):
        sim = _get_sim()
        sim.add_applied_field(picmi.ConstantAppliedField(Ez=1.0, By=2.0))
        sim.add_applied_field(
            picmi.AnalyticAppliedField(Ez_expression="3.0", Bx_function=lambda x, y, z, t: sympy.sin(x))
        )
        background = sim.get_as_pypicongpu().background_field
        assert background.ez == "4.0"
        assert background.by == "2.0"
        assert background.bx == "pmacc::math::sin(x)"

    def test_combined_parameters_are_merged(self):
        sim = _get_sim()
        sim.add_applied_field(picmi.AnalyticAppliedField(Ex_expression="a*x", a=2.0))
        sim.add_applied_field(picmi.AnalyticAppliedField(Ey_expression="b*y", b=3.0))
        background = sim.get_as_pypicongpu().background_field
        params = {p.name: p.value for p in background.user_defined_kw}
        assert params == {"a": 2.0, "b": 3.0}
        assert "a*x" in background.ex
        assert "b*y" in background.ey

    def test_conflicting_parameter_values_rejected(self):
        sim = _get_sim()
        sim.add_applied_field(picmi.AnalyticAppliedField(Ex_expression="a*x", a=2.0))
        sim.add_applied_field(picmi.AnalyticAppliedField(Ey_expression="a*y", a=3.0))
        with pytest.raises(UnsupportedFeatureError):
            sim.get_as_pypicongpu()

    def test_conflicting_influence_knobs_rejected(self):
        sim = _get_sim()
        sim.add_applied_field(picmi.ConstantAppliedField(Ez=1.0))
        sim.add_applied_field(picmi.ConstantAppliedField(Bz=1.0, picongpu_influences_dumps=False))
        with pytest.raises(UnsupportedFeatureError):
            sim.get_as_pypicongpu()

    def test_unsupported_applied_field_type_rejected(self):
        from picmistandard import PICMI_LoadGriddedField

        sim = _get_sim()
        # Standard PICMI applied fields that map to other C++ mechanisms
        # (injection/initialization) are not supported as background fields yet.
        sim.add_applied_field(picmi.AnalyticAppliedField(Ex_expression="1.0"))
        sim.add_applied_field(PICMI_LoadGriddedField(read_fields_from_path="/tmp/dummy.h5"))
        with pytest.raises(UnsupportedFeatureError):
            sim.get_as_pypicongpu()

    def test_region_bounds_rejected(self):
        sim = _get_sim()
        sim.add_applied_field(picmi.ConstantAppliedField(Ez=1.0, lower_bound=[0, 0, 0], upper_bound=[1e-6, 1e-6, 1e-6]))
        with pytest.raises(UnsupportedFeatureError):
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
        for key in (
            "ex",
            "ey",
            "ez",
            "bx",
            "by",
            "bz",
            "influence_particle_pusher",
            "influences_plugins",
            "influences_dumps",
        ):
            assert key in context["background_field"]
        # the renderer only accepts the standard leaf types
        assert isinstance(context["background_field"]["ey"], str)
        assert isinstance(context["background_field"]["influence_particle_pusher"], bool)

    def test_applied_field_from_constructor(self):
        grid = picmi.Cartesian3DGrid(
            number_of_cells=[16, 16, 16],
            lower_bound=[0, 0, 0],
            upper_bound=[16e-6, 16e-6, 16e-6],
            lower_boundary_conditions=["open", "open", "periodic"],
            upper_boundary_conditions=["open", "open", "periodic"],
        )
        solver = picmi.ElectromagneticSolver(method="Yee", grid=grid)
        sim = picmi.Simulation(
            time_step_size=1e-14,
            max_steps=4,
            solver=solver,
            applied_fields=[picmi.ConstantAppliedField(Ez=3e6)],
        )
        background = sim.get_as_pypicongpu().background_field
        assert isinstance(background, BackgroundField)
        assert background.ez == "3000000.0"

    def test_constant_lower_upper_bound_none_accepted(self):
        # the whole-domain case is the default (all-None bounds)
        applied_field = picmi.ConstantAppliedField(Ez=1.0)
        background = applied_field.get_as_pypicongpu()
        assert background.ez == "1.0"


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

    def _render_n_cfg(self, applied_field=None):
        import tempfile

        sim = _get_sim()
        if applied_field is not None:
            sim.add_applied_field(applied_field)
        with tempfile.TemporaryDirectory() as tmpdir:
            sim.write_input_file(Path(tmpdir) / "setup")
            cfg_path = Path(tmpdir) / "setup" / "etc" / "picongpu" / "N.cfg"
            return cfg_path.read_text()

    def test_default_rendering_equivalent_to_static_param(self):
        rendered = self._render_setup()
        static = STATIC_FIELDBACKGROUND_PARAM.read_text()
        assert _nonblank_lines(rendered) == _nonblank_lines(static)

    def test_default_rendering_n_cfg_has_no_field_background_option(self):
        # without a background the compatibility options are not rendered at all
        assert "fieldBackground.influences" not in self._render_n_cfg()

    def test_configured_rendering_enables_background(self):
        rendered = self._render_setup(picmi.ConstantAppliedField(Ey=1e6))
        assert "InfluenceParticlePusher = true" in rendered
        assert "1000000.0" in rendered
        # the J background stays off
        assert "FieldBackgroundJ" in rendered
        assert "activated = false" in rendered

    def test_configured_rendering_defaults_keep_pusher_plugins_dumps_on(self):
        rendered = self._render_setup(picmi.ConstantAppliedField(Ey=1e6))
        # both functors default to influence the pusher
        assert rendered.count("InfluenceParticlePusher = true") == 2
        cfg = self._render_n_cfg(picmi.ConstantAppliedField(Ey=1e6))
        assert "--fieldBackground.influencesPlugins true" in cfg
        assert "--fieldBackground.influencesDumps true" in cfg

    def test_configured_rendering_honours_influence_knobs(self):
        with pytest.warns(UserWarning, match="has no effect"):
            applied_field = picmi.ConstantAppliedField(
                Ey=1e6,
                picongpu_influence_particle_pusher=False,
                picongpu_influences_plugins=False,
                picongpu_influences_dumps=False,
            )
        rendered = self._render_setup(applied_field)
        # both functors render the configured value
        assert rendered.count("InfluenceParticlePusher = true") == 0
        assert rendered.count("InfluenceParticlePusher = false") == 2
        cfg = self._render_n_cfg(applied_field)
        assert "--fieldBackground.influencesPlugins false" in cfg
        assert "--fieldBackground.influencesDumps false" in cfg

    def test_configured_rendering_contains_analytic_expression(self):
        applied_field = picmi.AnalyticAppliedField(Ex_expression="1e5*sin(2*pi*y/wl)", wl=800e-9)
        rendered = self._render_setup(applied_field)
        assert "InfluenceParticlePusher = true" in rendered
        assert "pmacc::math::sin" in rendered
        # the parameter is rendered as a compile-time constant in the functors
        assert "constexpr float_64 wl =" in rendered

    def test_analytic_parameters_guarded_in_both_functors(self):
        # a parameter used only in the E expression must not trigger -Wunused-variable
        # in FieldBackgroundB (all parameter declarations carry [[maybe_unused]])
        applied_field = picmi.AnalyticAppliedField(Ex_expression="b0*cos(2*pi*y/wl)", b0=1e6, wl=800e-9)
        rendered = self._render_setup(applied_field)
        assert rendered.count("[[maybe_unused]] constexpr float_64 b0") == 2
        assert rendered.count("[[maybe_unused]] constexpr float_64 wl") == 2
