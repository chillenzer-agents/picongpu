"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: opencode
License: GPLv3+
"""

from picongpu.pypicongpu.output.binning import BinningAxis, BinSpec
from picongpu.pypicongpu.particle_functor.particle_functor import ParticleFunctor
from pytest import raises


def _axis(name: str) -> BinningAxis:
    return BinningAxis(
        name=name,
        functor=ParticleFunctor(name="dummy", functor_expression="x", functor_preamble=[], return_type="float"),
        bin_spec_raw=BinSpec(kind="linear", start=0, stop=1, nsteps=2),
        use_overflow_bins=True,
    )


def test_axis_name_allows_leading_digit_because_rendered_prefixed():
    # rendered C++ is `auto axis_{name}`, so a leading digit is fine
    assert _axis("0cold").axis_name == "0cold"


def test_axis_name_rejects_invalid_identifiers():
    with raises(ValueError, match="prefixed with 'axis_'|valid C\\+\\+ identifier"):
        _axis("cold 0")
