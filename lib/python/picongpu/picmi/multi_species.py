"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

import picmistandard

from picongpu.picmi.species import Species

# Wire the picmi-standard MultiSpecies factory up to our own Species class so that
# the member species it creates are full PIConGPU picmi species (carrying the
# PIConGPU-specific requirements, shapes, pushers, ...).
picmistandard.PICMI_MultiSpecies.Species_class = Species


class MultiSpecies(picmistandard.PICMI_MultiSpecies):
    """
    Multiple species that are initialised from one common initial distribution.

    PICMI-standard semantics (as implemented here): species are initialised
    **independently** by default; a ``MultiSpecies`` is the **explicit** mechanism
    to request **collective** (coordinated) initialisation. All member species share
    the same ``initial_distribution``, so on the C++ level they are placed with a
    single density operation (one ``CreateDensity``) and the remaining members are
    derived from the first one -- yielding exactly the same in-cell positions and
    hence a charge-neutral set-up by construction, irrespective of per-species
    momentum/temperature (which is applied afterwards, per species).

    Each member carries ``density_scale`` equal to its ``proportion``, which maps to
    the species' ``DensityRatio`` and is respected when deriving the members'
    weightings.

    The members are plain :class:`picmi.Species`. Add every member to your
    :class:`picmi.Simulation` via :meth:`picmi.Simulation.add_species`, typically
    with the same layout. Members whose layouts differ (in particular
    ``PseudoRandomLayout`` with different ``seed``) are deliberately initialised
    independently (force-independent discriminator, non-neutral on purpose).
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for member in self.species_instances_list:
            # Marker used by the operation-merging layer to identify coordinated
            # groups. Session-level only (survives deep-copies of a Simulation, as
            # all members reference the same instance); the merged result is what
            # survives serialization on the pypicongpu level.
            member._multi_species = self

    def __iter__(self):
        return iter(self.species_instances_list)
