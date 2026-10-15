"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

from typing import Literal

from pydantic import BaseModel, Field

from picongpu.pypicongpu import precision_config as pypicongpu_precision

from .copy_attributes import converts_to


@converts_to(pypicongpu_precision.PrecisionConfig)
class PrecisionConfig(BaseModel):
    """
    PIConGPU-specific numerical controls exposed at the PICMI level and rendered
    into ``include/picongpu/param/precision.param``.

    ``sqrt``, ``exp`` and ``trig`` select a special-operation namespace
    (``precisionSqrt`` / ``precisionExp`` / ``precisionTrigonometric``).
    ``"core"`` (default) aliases the core ``precisionPIConGPU`` precision, so a
    64-bit core does not silently downgrade these; ``32``/``64`` force
    ``precision32Bit``/``precision64Bit`` respectively.

    ``twts`` selects internal TWTSTight arithmetic using the same choices.
    ``twts_num_sigmas`` independently selects its envelope cutoff (default 6).
    Both TWTS settings apply to every pulse, for incident and background fields.
    """

    sqrt: Literal[32, 64, "core"] = "core"
    """precision of ``sqrt`` special operations (see ``precision.param``)."""

    exp: Literal[32, 64, "core"] = "core"
    """precision of ``exp`` special operations (see ``precision.param``)."""

    trig: Literal[32, 64, "core"] = "core"
    """precision of trigonometric special operations (see ``precision.param``)."""

    twts: Literal[32, 64, "core"] = "core"
    """Internal arithmetic for all TWTSTight pulses, independent of field storage precision."""

    twts_num_sigmas: int = Field(default=6, strict=True, gt=0, le=2**32 - 1)
    """TWTS envelope cutoff in multiples of tauG*c; does not change with precision automatically."""
