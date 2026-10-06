"""
This file is part of PIConGPU.
Copyright 2025 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

from pydantic import BaseModel

from ..rendering import RenderedObject


class SpeciesParticleBoundary(BaseModel, RenderedObject):
    """
    Resolved particle-boundary description for a single species.

    This is the per-axis result of "grid default combined with the species override" and carries
    the exact PIConGPU per-species command-line parameters:

    - ``boundary``: one C++ kind token per axis, e.g. ``"absorbing absorbing thermal"``
      (rendered as ``--<species>_boundary``);
    - ``offset``: optional inward offset per axis (int, >= 0), rendered as
      ``--<species>_boundaryOffset``;
    - ``temperature``: optional temperature per axis (keV, float, >= 0), rendered
      as ``--<species>_boundaryTemperature`` (only affects thermal boundaries).

    ``offset`` / ``temperature`` are rendered only when set (and non-empty), so a
    species that keeps all defaults emits just the ``--<species>_boundary`` line.
    """

    boundary: str
    """one particle-boundary kind token per axis (x y z), e.g. 'absorbing absorbing thermal'"""

    offset: str | None = None
    """space-separated per-axis inward offsets, or None if unused"""

    temperature: str | None = None
    """space-separated per-axis temperatures in keV, or None if unused"""
