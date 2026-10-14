"""
This file is part of PIConGPU.
Copyright 2025 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

from picmistandard import PICMI_Laser
from pydantic import Field

from ...pypicongpu import laser
from ..copy_attributes import default_converts_to


@default_converts_to(laser.FromOpenPMDPulseLaser)
class FromOpenPMDPulseLaser(PICMI_Laser):
    """
    PICMI object for FromOpenPMDPulseLaser.

    Analytic field (category B)
    ---------------------------
    The pulse is defined by the imported openPMD data, i.e. by its *input
    shape*; it is therefore a **category-B** laser and is only checked at the
    feed-in (Huygens) surface, never against bulk envelope properties.
    See ``lasers.rst``.
    """

    propagation_direction: list[float]
    polarization_direction: list[float]
    time_offset_si: float
    file_path: str
    iteration: int
    dataset_name: str
    datatype: str
    polarisationAxisOpenPMD: str
    propagationAxisOpenPMD: str
    picongpu_huygens_surface_positions: list[list[int]] = Field(
        default_factory=lambda: [[16, -16], [16, -16], [16, -16]]
    )
