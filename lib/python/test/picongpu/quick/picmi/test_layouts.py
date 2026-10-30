"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

import pytest
from pydantic import ValidationError
from pydantic_core import PydanticUndefined

from picongpu.picmi import GriddedLayout


def _field_errors(excinfo):
    return [error for error in excinfo.value.errors() if error["loc"] == ("n_macroparticles_per_cell",)]


def test_omitting_n_macroparticles_per_cell_fails_on_layout():
    with pytest.raises(ValidationError) as excinfo:
        GriddedLayout()

    errors = _field_errors(excinfo)
    assert errors
    assert errors[0]["type"] == "missing"


def test_field_has_no_mutable_default():
    assert GriddedLayout.model_fields["n_macroparticles_per_cell"].default is PydanticUndefined


def test_per_element_zero_is_rejected():
    with pytest.raises(ValidationError) as excinfo:
        GriddedLayout(n_macroparticles_per_cell=[1, 0, 1])

    assert _field_errors(excinfo)


def test_per_element_negative_is_rejected():
    with pytest.raises(ValidationError) as excinfo:
        GriddedLayout(n_macroparticles_per_cell=[1, -1, 1])

    assert _field_errors(excinfo)


def test_deprecated_singular_spelling_is_rejected():
    with pytest.raises((TypeError, ValidationError)):
        GriddedLayout(n_macroparticle_per_cell=[2, 2, 2])


def test_instances_do_not_share_their_particle_counts():
    first = GriddedLayout(n_macroparticles_per_cell=[1, 1, 1])
    second = GriddedLayout(n_macroparticles_per_cell=[1, 1, 1])

    first.n_macroparticles_per_cell.append(2)

    assert second.n_macroparticles_per_cell == [1, 1, 1]
    assert GriddedLayout(n_macroparticles_per_cell=[1, 1, 1]).n_macroparticles_per_cell == [1, 1, 1]
