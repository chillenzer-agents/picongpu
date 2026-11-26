"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: chillenzer-agents
License: GPLv3+

Hand-maintained registry of the predefined particle attributes.

The keys are the natural-language names accepted by ``particle.get(...)``
(spaces, no snake/camel/pascal case); the classes carry the C++ identifier plus
the metadata from ``include/picongpu/unitless/speciesAttributes.unitless``.  A
quick test parses ``speciesAttributes.param`` and this registry to guarantee
that every stored ``value_identifier`` has exactly one entry (aliases and flags
are excluded by construction).

The generated C++ keeps the stored identifier, e.g. ``"id"`` -> ``particleId``,
``"previous momentum"`` -> ``momentumPrev1``, ``"probe E"`` -> ``probeE`` and
``"charge state"`` -> ``boundElectrons``.  ``position`` maps to
``position<position_pic>``.

Registering a plugin- or atomic-physics-internal attribute only allocates its
storage on the species; it does not enable the consuming plugin and costs memory
per particle, so request only what a functor actually reads.

``totalCellIdx`` is deliberately **not** registered.  The openPMD plugin
appends it to its particle list unconditionally (``WriteSpecies.hpp`` and the
restart ``LoadSpecies.hpp`` build ``MakeSeq_t<..., totalCellIdx>`` without
deduplication), so a species that also declared it would trigger a
duplicate-attribute static assert.  The attribute remains an internal detail of
that plugin and is not functor-facing.
"""

from .accepted import Accepted
from .atomic_state_collection_index import AtomicStateCollectionIndex
from .bin_index import BinIndex
from .boundelectrons import BoundElectrons
from .momentum import Momentum
from .momentum_prev_1 import MomentumPrev1
from .particle_id import ParticleId
from .position import Position
from .probe_b import ProbeB
from .probe_e import ProbeE
from .process_class import ProcessClass
from .radiation_mask import RadiationMask
from .transition_index import TransitionIndex
from .transition_radiation_mask import TransitionRadiationMask
from .weighting import Weighting
from .weighting_damping_factor import WeightingDampingFactor

ATTRIBUTE_REGISTRY: dict[str, type] = {
    "position": Position,
    "id": ParticleId,
    "momentum": Momentum,
    "previous momentum": MomentumPrev1,
    "weighting": Weighting,
    "weighting damping factor": WeightingDampingFactor,
    "probe E": ProbeE,
    "probe B": ProbeB,
    "radiation mask": RadiationMask,
    "transition radiation mask": TransitionRadiationMask,
    "charge state": BoundElectrons,
    "atomic state collection index": AtomicStateCollectionIndex,
    "atomic state process class": ProcessClass,
    "atomic state transition index": TransitionIndex,
    "atomic state bin index": BinIndex,
    "atomic state transition accepted": Accepted,
}
# ``totalCellIdx`` is intentionally absent: the openPMD plugin already adds it
# to its particle list (see the module docstring).  The registry coverage test
# carries the explicit exclusion so it cannot silently drift.


# Derived accessors that are not stored attributes but still have a
# well-defined value type/weighting behaviour.  They are intentionally not part
# of the species registry (they need no extra attribute storage).
DERIVED_ACCESSORS: dict[str, dict] = {
    "mass": {"cpp_type": "float_X", "weighting_power": 1},
    "charge": {"cpp_type": "float_X", "weighting_power": 1},
    "gamma": {"cpp_type": "float_X"},
    "kinetic energy": {"cpp_type": "float_X", "weighting_power": 1},
    "velocity": {"cpp_type": "float3_X", "n_components": 3},
    "damped weighting": {"cpp_type": "float_X"},
    "timestep": {"cpp_type": "uint32_t"},
    "timestep size": {"cpp_type": "float_X"},
}


def attribute_class(name: str) -> type | None:
    """Return the registry class for a functor-facing attribute name."""
    return ATTRIBUTE_REGISTRY.get(name)


def attribute_for_name(name: str):
    """Instantiate the registered attribute for a functor-facing name."""
    cls = attribute_class(name)
    return None if cls is None else cls()
