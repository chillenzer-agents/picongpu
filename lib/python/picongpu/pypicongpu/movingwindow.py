"""
This file is part of the PIConGPU.
Copyright 2024-2025 PIConGPU contributors
Authors: Brian Edward Marre, Julian Lenz
License: GPLv3+
"""

from typing import Annotated

from pydantic import BaseModel, Field

from .rendering import RenderedObject


class MovingWindow(RenderedObject, BaseModel):
    """
    Moving window of a PIConGPU simulation.

    The window slides in the +y direction with the speed of light (this is a
    PIConGPU design choice: the window speed is fixed to c, so there is no
    speed field and no velocity < c constraint to validate here).

    Rendered into the batch submission configuration (etc/picongpu/N.cfg:
    --windowMovePoint / --stopWindow).

    Units policy: move_point is a length in units of the simulation window
    size; stop_iteration is a time-step index.
    """

    move_point: Annotated[float, Field(..., ge=0.0)]
    """
    point a light ray reaches in y from the left border until we begin sliding the simulation window with the speed of
    light, in multiples of the simulation window size, [dimensionless]; must be >= 0.
    C++ name: --windowMovePoint (etc/picongpu/N.cfg).

    @attention if moving window is active, one gpu in y direction is reserved for initializing new spaces,
        thereby reducing the simulation window size according
    """

    stop_iteration: Annotated[int, Field(gt=0.0)] | None
    """iteration, at which to stop moving the simulation window, [dimensionless]; must be > 0 when set.
    C++ name: --stopWindow (etc/picongpu/N.cfg)."""
