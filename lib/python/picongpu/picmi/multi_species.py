"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

from copy import copy, deepcopy

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

    .. note::

       The grouping is tracked by a private per-member marker
       (``Species._multi_species``). It survives deep-copies of a
       :class:`picmi.Simulation` (all members reference the same
       ``MultiSpecies`` instance) but is **not** part of any serialized
       representation of a species: a pydantic ``model_dump``/``model_validate``
       round-trip does not preserve it. The picmi layer has no such
       serialization surface today; the pypicongpu layer is the serialization
       surface and stores the *result* of the grouping (the ``created`` species
       plus the ``derived`` members) explicitly, so a round-trip through
       pypicongpu keeps the merged/charge-neutral setup intact.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for member in self.species_instances_list:
            # Marker used by the operation-merging layer to identify coordinated
            # groups. Session-level only (survives deep-copies of a Simulation, as
            # all members reference the same instance); the merged result is what
            # survives serialization on the pypicongpu level.
            member._multi_species = self

    def __deepcopy__(self, memo=None):
        # pydantic's ``BaseModel.__deepcopy__`` does not register the new
        # instance in ``memo`` before copying its private attributes, so the
        # ``_multi_species`` marker (which points back at this object) would be
        # deep-copied once per member. Each member would then reference a
        # *different* copy of the group, and the operation-merging layer would
        # no longer recognise them as coordinated. Register the copy up-front
        # and re-point every copied member at it.
        memo = {} if memo is None else memo
        cls = type(self)
        new = cls.__new__(cls)
        memo[id(self)] = new
        object.__setattr__(new, "__dict__", deepcopy(self.__dict__, memo))
        object.__setattr__(new, "__pydantic_extra__", deepcopy(self.__pydantic_extra__, memo))
        object.__setattr__(new, "__pydantic_fields_set__", copy(self.__pydantic_fields_set__))
        object.__setattr__(new, "__pydantic_private__", deepcopy(self.__pydantic_private__, memo))
        for member in new.species_instances_list:
            member._multi_species = new
        return new

    def __iter__(self):
        return iter(self.species_instances_list)
