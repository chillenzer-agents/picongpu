"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: opencode
License: GPLv3+
"""

from picongpu.pypicongpu.rendering.renderer import Renderer
from pytest import raises


def test_scalar_list_accepts_numbers():
    Renderer.check_rendering_context({"modes": [1.0, 2, 3.5]})


def test_scalar_list_rejects_math_nan():
    import math

    with raises(ValueError):
        Renderer.check_rendering_context({"modes": [1.0, math.nan]})


def test_scalar_list_rejects_call_provided_nan():
    with raises(ValueError):
        Renderer.check_rendering_context({"modes": [1.0, float("nan")]})


def test_scalar_list_rejects_math_inf():
    import math

    with raises(ValueError):
        Renderer.check_rendering_context({"modes": [1.0, math.inf, -math.inf]})


def test_leaf_rejects_call_provided_nan():
    with raises(ValueError):
        Renderer.check_rendering_context({"wavelength": float("nan")})


def test_leaf_rejects_math_inf():
    import math

    with raises(ValueError):
        Renderer.check_rendering_context({"wavelength": math.inf})
