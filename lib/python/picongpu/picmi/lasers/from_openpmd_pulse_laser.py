"""
This file is part of PIConGPU.
Copyright 2025 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

import numpy as np
from picmistandard import PICMI_Laser
from pydantic import Field, model_validator

from ...pypicongpu import laser
from ..copy_attributes import default_converts_to
from .base_laser import BaseLaser


@default_converts_to(laser.FromOpenPMDPulseLaser)
class FromOpenPMDPulseLaser(PICMI_Laser, BaseLaser):
    """PICMI object for FromOpenPMDPulseLaser.

    Entry faces: like the standard lasers, this pulse is injected through the
    coordinate faces its ``propagation_direction`` crosses (see
    :meth:`BaseLaser._entry_faces`), and ``picongpu_entry_faces`` may override
    the derived set (it is no longer rejected for this laser type). This works
    because the profile is a face-agnostic ``profiles::FromOpenPMDPulse`` at
    the C++ layer: the solver accepts any profile under any face list,
    duplicates included, so the same ``on_XMin...on_ZMax`` multi-face machinery
    applies. The core requires an axis-parallel direction for this profile
    (checked below), so the *derived* face list is always exactly one face
    (``+x`` -> ``XMin``, ``-y`` -> ``YMax``, ...); an explicit
    ``picongpu_entry_faces`` may still list several.

    The frontend does not police the face-vs-direction consistency of explicit
    lists, nor the relation between the record axes and the direction:
    ``propagationAxisOpenPMD`` names the axis the stored record runs along and
    does not have to coincide with the direction's axis: the core
    (``OpenPMDdata<T_Params>``) aligns the record's propagation axis with the
    simulation's propagation axis and rotates the stored data accordingly.
    Two core caveats remain the user's responsibility:

    * each distinct from-openPMD profile loads one on-device dataset per
      parameter type at t=0 (``OpenPMDdata<T_Params>::get()``), so listing the
      same pulse under several faces shares that one dataset (memory, not
      correctness);
    * an explicit face list the direction does not head for is physically
      meaningless even though the core accepts it (the derived list always
      does head for its faces).

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

    @model_validator(mode="after")
    def _validate(self):
        self._validate_norms()
        self._validate_directions_axis_parallel()
        return self

    def _validate_norms(self):
        """Normalization and orthogonality of the direction/polarization vectors.

        Deliberately not the full :meth:`BaseLaser._validate_common_properties`:
        a FromOpenPMD pulse has no ``centroid_position`` (the record is
        positioned at the Huygens surface along the propagation direction,
        with the arrival time set by ``time_offset_si``; the core times the
        record against ``currentStep * dt`` time-delayed by that offset), so
        the standard lasers' centroid-outside-the-box-per-entry-face check does
        not apply.
        """
        if not np.allclose(n := np.linalg.norm(self.propagation_direction), 1):
            raise ValueError(
                "The propagation direction vector must be normalized. "
                f"You gave propagation_direction={self.propagation_direction} with norm {n}."
            )
        if not np.allclose(n := np.linalg.norm(self.polarization_direction), 1):
            raise ValueError(
                "The polarization direction vector must be normalized. "
                f"You gave polarization_direction={self.polarization_direction} with norm {n}."
            )
        if abs(float(np.dot(self.polarization_direction, self.propagation_direction))) > 1.0e-4:
            # the core's compile-time assert uses the same 1e-4 band
            raise ValueError(
                "The polarization direction must be orthogonal to the propagation direction. "
                f"You gave polarization_direction={self.polarization_direction} and "
                f"propagation_direction={self.propagation_direction}."
            )

    def _validate_directions_axis_parallel(self):
        """The direction and polarization must each lie on a single coordinate axis.

        The C++ profile enforces this at compile time (``FromOpenPMDPulse.hpp``:
        both vectors must be limited to one axis, because the stored record
        resolves the time delay along a single axis only); this mirrors the
        core's 0.9999/1.0001 tolerance band so the frontend rejects exactly
        what the core would refuse to compile, as a readable error instead of
        a C++ compile failure.
        """
        for label, vector in (
            ("propagation", self.propagation_direction),
            ("polarization", self.polarization_direction),
        ):
            components = [float(component) for component in vector]
            squares = [component * component for component in components]
            if not any(0.9999 <= square <= 1.0001 for square in squares):
                axis = max(range(3), key=lambda i: abs(components[i]))
                name = "xyz"[axis]
                raise ValueError(
                    f"For the FromOpenPMD pulse the {label} direction must be an "
                    "axis-parallel unit vector (the record resolves the time delay along a "
                    f"single axis only, so the core rejects {label} directions that are not "
                    f"aligned with one of the coordinate axes). The dominant component is "
                    f"{components[axis]:.6g} along '{name}' but is not (close to) +/-1. You gave "
                    f"{label}_direction={vector}."
                )
