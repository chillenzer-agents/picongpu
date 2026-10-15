"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+

Pure, graphlib-based PICMI -> PyPIConGPU translation (issue #107).

`translate(sim)` reproduces what `Simulation.get_as_pypicongpu()` produces while
observing the invariants that the incumbent, `__init__`-registration-based path
does not:

* Purity: the input `picmi.Simulation` (and every member) is never mutated. The
  translation works on a fresh, internally-owned copy that is discarded when the
  function returns.
* Reachability: only objects reachable from `sim` contribute constraints. This
  fixes upstream #5727 by itself: an `IonizationModel` that is constructed but
  never added to `picongpu_interaction` is not reachable, so `translate` derives
  no ionization onto its species -- whether or not the incumbent `__init__`
  polluted the source object. `translate` is therefore independent of the
  `__init__`-level registration switch (`INIT_MUTATION_ENABLED`).

Design (per the resolved spec in #107):
1. Walk the reachable PICMI object graph from `sim` (BFS over pydantic fields,
   visited by `id`).
2. Order the reachable objects so that referenced objects come before their
   referrers, using `graphlib.TopologicalSorter` (this also surfaces reference
   cycles as `graphlib.CycleError`).
3. Resolve bottom-up over that order: for each reachable species, discard the
   cross-object requirements the incumbent `__init__` may have pre-registered,
   then re-derive them from the reachable cross-object objects (interactions,
   diagnostics) via `_apply_cross_object_constraints`. This is what makes the
   output depend on reachability alone, and it makes the topological order
   load-bearing: a referrer's re-derivation must run after its referenced species
   has been reset.
4. The `pypicongpu.Simulation` tree is constructed from the resolved copy by
   reusing the incumbent per-class `get_as_pypicongpu` methods (kept as the
   reference path, Q4). Conflict/uniqueness semantics are those of the incumbent
   `species_requirements.resolving_add`/`check_for_conflict` (see `translate`).
"""

import graphlib
from collections import deque
from enum import Enum
from typing import Any, Iterator

import numpy as np

from pydantic import BaseModel

from picongpu.pypicongpu.species.attribute.boundelectrons import BoundElectrons
from picongpu.pypicongpu.species.attribute.momentum_prev_1 import MomentumPrev1
from picongpu.pypicongpu.species.attribute.radiation_mask import RadiationMask
from picongpu.pypicongpu.species.constant.elementproperties import ElementProperties

from .diagnostics.radiation import Radiation
from .interaction.ionization.ionizationmodel import IonizationModel
from .interaction.synchrotron import Synchrotron
from .species import DependsOn
from .species import Species as PICMI_Species
from .species_requirements import (
    DelayedConstruction,
    GroundStateIonizationConstruction,
    SetChargeStateOperation,
    SynchrotronConstantConstruction,
)


class Walk:
    """BFS over the reachable PICMI object graph, visited by `id`."""

    def __init__(self, root):
        self._queue = deque([root])
        self._seen: set[int] = set()

    def objects(self) -> Iterator[BaseModel]:
        while self._queue:
            obj = self._queue.popleft()
            if id(obj) in self._seen:
                continue
            self._seen.add(id(obj))
            if isinstance(obj, BaseModel):
                yield obj
            for value in _referenced(obj):
                if id(value) not in self._seen:
                    self._queue.append(value)

    def __iter__(self):
        return self.objects()


def _referenced(obj) -> list[Any]:
    """Object-valued pydantic fields of `obj` (the cross-object references)."""
    refs = []
    if isinstance(obj, BaseModel):
        for value in obj.__dict__.values():
            refs.extend(_iter_refs(value))
        if obj.__pydantic_private__:
            for value in obj.__pydantic_private__.values():
                refs.extend(_iter_refs(value))
    return refs


def _is_requirement(obj) -> bool:
    # Requirement carriers (DelayedConstruction, DependsOn) reference their owner
    # species, which would create reference cycles. They are internal metadata and
    # never reach PICMI objects beyond what is already reachable, so they are not
    # graph nodes.
    return isinstance(obj, (DelayedConstruction, DependsOn))


def _iter_refs(value) -> Iterator[Any]:
    if isinstance(value, BaseModel):
        if not _is_requirement(value):
            yield value
    elif isinstance(value, (list, tuple, set, frozenset)):
        for item in value:
            yield from _iter_refs(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _iter_refs(item)


# Pydantic keeps these slots outside `__dict__`; they must be carried over for a
# copy to render correctly.
_PYDANTIC_SLOTS = (
    "__pydantic_private__",
    "__pydantic_fields_set__",
    "__pydantic_extra__",
    "__pydantic_extra_info__",
    "__pydantic_computed_fields__",
)


def _shallow_copy(model: BaseModel) -> BaseModel:
    """Shallow copy of a pydantic model.

    Uses `model_copy(deep=False)`, but falls back to rebuilding the instance via
    `object.__new__` when the class customises `__new__` (e.g. the
    `@decorating_class` functors such as `ParticleFunctor` and
    `AnalyticDistribution`), where `model_copy`'s zero-argument reconstruction is
    hijacked by the decorator's `__new__` and returns a decorator-caller instead
    of an instance. Either way the private-attribute dict is replaced by a fresh
    (shallow) dict so that deepening the copy never mutates the source.
    """
    new = model.model_copy(deep=False)
    if type(new) is not type(model):
        new = object.__new__(type(model))
        new.__dict__ = dict(vars(model))
        for name in _PYDANTIC_SLOTS:
            try:
                value = object.__getattribute__(model, name)
            except AttributeError:
                continue
            try:
                object.__setattr__(new, name, value)
            except Exception:
                continue
    try:
        private = object.__getattribute__(new, "__pydantic_private__")
    except AttributeError:
        private = None
    if private is not None:
        object.__setattr__(new, "__pydantic_private__", dict(private))
    return new


def deep_copy(obj, seen: dict[int, BaseModel]) -> Any:
    """Pure, memoised, structure-preserving deep copy of a PICMI object graph.

    Nested `BaseModel`s (including those buried in private attributes and in the
    `metadata` of requirement objects) are all re-copied while staying
    referentially consistent. Scalars and callables are shared; the result is a
    disjoint copy that can be mutated without affecting the input.
    """
    if isinstance(obj, BaseModel):
        if (existing := seen.get(id(obj))) is not None:
            return existing
        new = _shallow_copy(obj)
        seen[id(obj)] = new
        for key, value in list(new.__dict__.items()):
            new.__dict__[key] = deep_copy(value, seen)
        if new.__pydantic_private__:
            for key, value in list(new.__pydantic_private__.items()):
                new.__pydantic_private__[key] = deep_copy(value, seen)
        return new
    if isinstance(obj, dict):
        return {key: deep_copy(value, seen) for key, value in obj.items()}
    if isinstance(obj, (list, tuple)):
        copied = [deep_copy(value, seen) for value in obj]
        return tuple(copied) if isinstance(obj, tuple) else copied
    if isinstance(obj, (set, frozenset)):
        return type(obj)(deep_copy(value, seen) for value in obj)
    return obj


def build_constraint_graph(sim) -> dict[int, list[int]]:
    """Return {id(object): [id(referenced objects)]} for the reachable graph.

    Pydantic models are unhashable, so nodes are keyed by `id()`.
    """
    adjacency: dict[int, list[int]] = {}
    for obj in Walk(sim):
        adjacency[id(obj)] = [id(ref) for ref in _referenced(obj) if isinstance(ref, BaseModel)]
    return adjacency


def topological_order(sim) -> list[BaseModel]:
    """Order the reachable objects so that referenced objects come before their
    referrers, using `graphlib.TopologicalSorter` (cycle detection included).

    Edits that would create a dependency cycle surface as
    `graphlib.CycleError` here rather than as silent mistranslation.
    """
    by_id: dict[int, BaseModel] = {}
    for obj in Walk(sim):
        by_id[id(obj)] = obj
    adjacency = build_constraint_graph(sim)
    sorter = graphlib.TopologicalSorter()
    for obj in Walk(sim):
        sorter.add(id(obj), *(adjacency[id(obj)]))
    return [by_id[node] for node in sorter.static_order()]


def _redrive_ionization(obj: IonizationModel) -> None:
    ion = obj.ion_species
    ion.register_requirements(
        [
            DependsOn(species=obj.ionization_electron_species),
            GroundStateIonizationConstruction(ionization_model=obj),
            SetChargeStateOperation(species=ion),
            BoundElectrons(),
        ]
    )
    ion.register_requirements(obj.get_constants())


def _redrive_synchrotron(obj: Synchrotron) -> None:
    obj.electron_species.register_requirements(
        [
            DependsOn(species=obj.photon_species),
            SynchrotronConstantConstruction(photon_species=obj.photon_species),
        ]
    )


def _redrive_radiation(obj: Radiation) -> None:
    for species in obj.species:
        species.register_requirements(
            [MomentumPrev1()] + ([RadiationMask()] if obj.gamma_filter_threshold is not None else [])
        )


# The re-derivation table (issue #107, Q1 extension point): a declarative list of
# (cross-object object type, re-deriver) pairs. Every cross-object constraint that
# the incumbent path registers eagerly in `__init__` is re-derived from the
# reachable object here instead, so adding a fourth cross-object constraint is a
# one-line addition to this table (plus a matching entry in
# `_CROSS_OBJECT_REQUIREMENTS` below).
_CROSS_OBJECT_REDERIVERS: tuple[tuple[type, Any], ...] = (
    (IonizationModel, _redrive_ionization),
    (Synchrotron, _redrive_synchrotron),
    (Radiation, _redrive_radiation),
)


def _apply_cross_object_constraints(obj: BaseModel) -> None:
    """(Re)apply the cross-object constraints that `obj` imposes on other objects.

    Data-driven over `_CROSS_OBJECT_REDERIVERS`: the re-derivation is a
    declarative table of (detector type, re-deriver) pairs, so a fourth
    cross-object constraint is a one-line addition. It applies *exactly* the
    constraints the incumbent `__init__` registers, but only to the copy (never
    the input) and only because `obj` is reachable from the simulation. All
    other constraints (one-to-one rendering and per-class value constraints) are
    reproduced by the incumbent per-class `get_as_pypicongpu` against the copy.
    """
    for detector, redrive in _CROSS_OBJECT_REDERIVERS:
        if isinstance(obj, detector):
            redrive(obj)
            return


# The cross-object requirements that the incumbent path registers eagerly in
# `__init__` (behind `INIT_MUTATION_ENABLED`) and that `_apply_cross_object_
# constraints` re-derives from reachable objects. These are exactly the types the
# switch-gated `__init__` methods add, and nothing else.
_CROSS_OBJECT_REQUIREMENTS = (
    DependsOn,
    GroundStateIonizationConstruction,
    SetChargeStateOperation,
    BoundElectrons,
    SynchrotronConstantConstruction,
    ElementProperties,
    MomentumPrev1,
    RadiationMask,
)


def _reset_cross_object_requirements(species: PICMI_Species) -> None:
    """Strip the incumbent-registered cross-object requirements from a species copy.

    `translate` discards these (which may include incumbent `__init__` pollution
    carried into the copy) and re-derives them from reachability alone via
    `_apply_cross_object_constraints`. This is what makes the output independent
    of `INIT_MUTATION_ENABLED` and fixes #5727.
    """
    species._requirements = [
        requirement for requirement in species._requirements if not isinstance(requirement, _CROSS_OBJECT_REQUIREMENTS)
    ]


def translate(sim):
    """Pure, reachability-driven PICMI -> PyPIConGPU translation of `sim`.

    Returns the `pypicongpu.Simulation` produced by a fresh, internally-owned
    copy of `sim` resolved bottom-up (topological order), and never mutates `sim`
    or any of its members. For every well-formed `sim` built through the incumbent
    path (`INIT_MUTATION_ENABLED` on), the result matches
    `sim.get_as_pypicongpu()` under normalisation (see the Q2 equality test).

    Cross-object requirements are discarded from every reachable species and
    re-derived from the reachable cross-object objects, so the output depends on
    reachability alone and is independent of `INIT_MUTATION_ENABLED` (this is
    what fixes #5727). The topological order is load-bearing: a species must be
    reset before any reachable referrer re-derives onto it.

    Conflict/uniqueness semantics are those of the incumbent
    `species_requirements.resolving_add`/`check_for_conflict`: `translate` routes
    every requirement through `Species.register_requirements`, so a genuinely
    conflicting requirement (e.g. two disagreeing `Mass`/`Charge`/attribute
    constants) raises `RequirementConflict` rather than being silently merged.
    """
    context = {}
    resolved = deep_copy(sim, context)
    # Resolve bottom-up: referenced objects (grid, solver, species, layouts,
    # distributions, ...) before their referrers (interactions, diagnostics).
    # Reset each reachable species, then re-derive its cross-object requirements
    # from reachability. Also surfaces any reference cycle via
    # graphlib.CycleError (topological_order).
    for obj in topological_order(resolved):
        if isinstance(obj, PICMI_Species):
            _reset_cross_object_requirements(obj)
        _apply_cross_object_constraints(obj)
    return resolved.get_as_pypicongpu()


def normalize(model):
    """Return a normalised, plain-Python structural view of a pypicongpu object.

    Recurses over the *declared* fields of every pydantic model, so computed
    fields (notably the uuid-derived `ParticleFunctor.typename`) and private state
    are excluded by construction, and no custom `model_serializer` (which can have
    filesystem side effects) is invoked. Leaves are canonicalised: enums to their
    value, callables to a placeholder, and anything non-trivial (e.g. a sympy
    expression) to its `repr`. The result is a hash-free, side-effect-free
    structure suitable for the Q2 `==` comparison.
    """
    return _normalize_value(model)


def _normalize_value(value):
    if isinstance(value, BaseModel):
        data = value.__dict__
        return {name: _normalize_value(data[name]) for name in type(value).model_fields if name in data}
    if isinstance(value, dict):
        return {key: _normalize_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return tuple(_normalize_value(item) for item in value)
    if isinstance(value, set):
        return {_normalize_value(item) for item in value}
    if isinstance(value, Enum):
        return value.value
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, np.generic):
        return value.item()
    if callable(value):
        return "<callable>"
    return repr(value)
