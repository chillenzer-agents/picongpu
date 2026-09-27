"""
This file is part of PIConGPU.
Copyright 2021-2024 PIConGPU contributors
Authors: Hannes Troepgen, Brian Edward Marre
License: GPLv3+
"""

from ...pypicongpu import species

import picmistandard

"""
note on rms_velocity:
--------------------
The rms_velocity is converted to a temperature in keV. This conversion requires the mass of the species to be known,
which is not the case inside the picmi density distribution.

As an abstraction, **every** PICMI density distribution implements `picongpu_get_rms_velocity_si()` which returns a
tuple (float, float, float) with the rms_velocity per axis in SI units (m/s).

In case the density profile does not have an rms_velocity, this method **MUST** return (0, 0, 0), which is translated to
"no temperature initialization" by the owning species.

note on drift:
--------------
The drift ("velocity") is represented using either directed_velocity or centroid_velocity (v, gamma*v respectively) and
for the pypicongpu representation stored in a separate object (Drift).

To accommodate that, this separate Drift object can be requested by the method get_picongpu_drift(). In case of no drift,
this method returns None.
"""


def _as_bound(bound) -> tuple[float | None, float | None, float | None] | None:
    """
    Convert a PICMI bound (list of length 3, a ``None`` axis = unbounded) to
    the pypicongpu 3-component tuple representation.
    """
    if bound is None or all(component is None for component in bound):
        return None
    return tuple(bound)


class UniformDistribution(picmistandard.PICMI_UniformDistribution):
    """Uniform Particle Distribution as defined by PICMI"""

    def picongpu_get_rms_velocity_si(self) -> tuple[float, float, float]:
        return tuple(self.rms_velocity)

    def get_as_pypicongpu(self, grid):
        profile = species.operation.densityprofile.Uniform(
            density_si=self.density,
            lower_bound=_as_bound(self.lower_bound),
            upper_bound=_as_bound(self.upper_bound),
            fill_in=self.fill_in,
        )

        return profile

    def get_picongpu_drift(self) -> species.operation.momentum.Drift | None:
        """
        Get drift for pypicongpu
        :return: pypicongpu drift object or None
        """
        if [0, 0, 0] == self.directed_velocity:
            return None
        return species.operation.momentum.Drift.from_velocity(tuple(self.directed_velocity))

    def __call__(self, x, y, z):
        return 0.0 * (x + y + z) + self.density
