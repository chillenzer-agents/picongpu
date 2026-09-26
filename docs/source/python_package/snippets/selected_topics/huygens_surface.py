#!/usr/bin/env python
# /// script
# requires-python = ">=3.11,<3.14"
# dependencies = [
#   "picongpu @ git+https://github.com/ComputationalRadiationPhysics/picongpu@dev#subdirectory=lib/python"
# ]
# ///
"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+

An incident-field laser with an explicit Huygens surface position:
16 cells in from each of the low edges and 16 cells in from each of the
high edges of the global domain.
"""

# BEGIN-HUYGENS-SURFACE
from picongpu import picmi

laser = picmi.GaussianLaser(
    wavelength=0.8e-6,
    waist=5.0e-6,
    duration=5.0e-15,
    propagation_direction=[0.0, 1.0, 0.0],
    polarization_direction=[1.0, 0.0, 0.0],
    focal_position=[1e-6, 1.5e-6, 1e-6],
    # the pulse centroid at time zero must be outside of the box:
    centroid_position=[1e-6, -1.5e-5, 1e-6],
    a0=8.0,
    # one [min, max] pair of cell indices per axis (x, y, z);
    # a negative max counts cells in from the high edge:
    picongpu_huygens_surface_positions=[[16, -16], [16, -16], [16, -16]],
)
# END-HUYGENS-SURFACE

print("accepted Huygens surface positions:", laser.picongpu_huygens_surface_positions)
