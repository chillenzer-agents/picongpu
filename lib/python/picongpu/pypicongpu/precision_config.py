"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

from typing import Literal

from pydantic import BaseModel, Field, computed_field


class PrecisionConfig(BaseModel):
    """
    Special-operation precision and shared TWTS numerical controls rendered into
    ``include/picongpu/param/precision.param``.

    ``sqrt``, ``exp`` and ``trig`` select special-operation namespaces;
    ``twts`` selects internal TWTSTight arithmetic.
    ``"core"`` (default) aliases the core ``precisionPIConGPU`` precision, so a
    64-bit core does not silently downgrade these; ``32``/``64`` force
    ``precision32Bit``/``precision64Bit`` respectively.

    ``twts_num_sigmas`` independently selects the TWTS envelope cutoff.
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
    """TWTS envelope cutoff in multiples of tauG*c."""

    @computed_field
    def twts_precision_bits(self) -> int:
        """Zero selects the simulation's float_X in the C++ configuration."""
        return 0 if self.twts == "core" else self.twts
