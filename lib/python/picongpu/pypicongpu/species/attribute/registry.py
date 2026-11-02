"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: chillenzer-agents
License: GPLv3+

Hand-maintained registry of the predefined particle attributes.

The keys are the names accepted by ``particle.get(...)``; the classes carry
the C++ identifier plus the metadata from
``include/picongpu/unitless/speciesAttributes.unitless``.  A quick test parses
``speciesAttributes.param`` and this registry to guarantee that every stored
``value_identifier`` has exactly one entry (aliases and flags are excluded by
construction).

The registry maps historical functor names where they differ from the stored
identifier: ``position`` -> ``position_pic`` and
``charge_state`` -> ``boundElectrons``.
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
from .total_cell_idx import TotalCellIdx
from .transition_index import TransitionIndex
from .transition_radiation_mask import TransitionRadiationMask
from .weighting import Weighting
from .weighting_damping_factor import WeightingDampingFactor

ATTRIBUTE_REGISTRY: dict[str, type] = {
    "position": Position,
    "particleId": ParticleId,
    "momentum": Momentum,
    "momentumPrev1": MomentumPrev1,
    "weighting": Weighting,
    "weightingDampingFactor": WeightingDampingFactor,
    "probeE": ProbeE,
    "probeB": ProbeB,
    "radiationMask": RadiationMask,
    "transitionRadiationMask": TransitionRadiationMask,
    "charge_state": BoundElectrons,
    "atomicStateCollectionIndex": AtomicStateCollectionIndex,
    "processClass": ProcessClass,
    "transitionIndex": TransitionIndex,
    "binIndex": BinIndex,
    "accepted": Accepted,
    "totalCellIdx": TotalCellIdx,
}

# Derived accessors that are not stored attributes but still have a
# well-defined value type/weighting behaviour.  They are intentionally not part
# of the species registry (they need no extra attribute storage).
DERIVED_ACCESSORS: dict[str, dict] = {
    "mass": {"cpp_type": "float_X"},
    "charge": {"cpp_type": "float_X"},
    "gamma": {"cpp_type": "float_X"},
    "kinetic energy": {"cpp_type": "float_X"},
    "velocity": {"cpp_type": "float_X", "n_components": 3},
    "damped_weighting": {"cpp_type": "float_X"},
    "timestep": {"cpp_type": "uint32_t"},
    "timestep_size": {"cpp_type": "float_X"},
}


def attribute_class(name: str) -> type | None:
    """Return the registry class for a functor-facing attribute name."""
    return ATTRIBUTE_REGISTRY.get(name)


def attribute_for_name(name: str):
    """Instantiate the registered attribute for a functor-facing name."""
    cls = attribute_class(name)
    return None if cls is None else cls()
