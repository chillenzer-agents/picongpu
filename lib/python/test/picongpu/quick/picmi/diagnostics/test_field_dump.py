"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
License: GPLv3+

The former template-rendering tests for the removed ``derived_fields``
species-eligibility narrowing now live in ``test_derived_field_dump.py`` and
``test_openpmd_derived_fields.py`` (the ``field_tmp_solvers`` mechanism). What
remains here is the independent openPMD ``range`` serialisation regression.
"""

import pytest

from picongpu.picmi import diagnostics as diag
from picongpu.picmi.diagnostics.backend_config import RangeSpec


@pytest.mark.parametrize(
    "bounds, expected",
    [
        ((None, None, None), ":,:,:"),
        (((1780, 1804), None, None), "1780:1804,:,:"),
        ((None, (1780, 1804), None), ":,1780:1804,:"),
        ((None, None, (884, 908)), ":,:,884:908"),
    ],
)
@pytest.mark.parametrize("as_object", [False, True])
def test_range_preserves_axis_positions(bounds, expected, as_object):
    # C++ toRangeSlice skips empty components, so commas alone are insufficient.
    config = diag.OpenPMDConfig(file="fields", range=RangeSpec(*bounds) if as_object else bounds)
    assert config.model_dump(mode="json")["range"] == expected
