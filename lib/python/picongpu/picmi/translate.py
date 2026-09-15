"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

"""
Pure, graphlib-based PICMI -> PyPIConGPU translation (issue #107).

`translate(sim)` reproduces what `Simulation.get_as_pypicongpu()` produces while
observing the invariants that the incumbent, `__init__`-registration-based path
does not:

* Purity: the input `picmi.Simulation` (and every member) is never mutated. The
  translation works on a fresh, internally-owned copy that is discarded when the
  function returns.
* Reachability: only objects reachable from `sim` contribute constraints. This is
  what fixes upstream #5727 (an `IonizationModel` that is constructed but never
  added to `picongpu_interaction` must not pollute the ion species) once the
  `__init__`-level registration switch (see `INIT_MUTATION_ENABLED` below) is off.

Design (per the resolved spec in #107):
1. Walk the reachable PICMI object graph from `sim` (BFS over pydantic fields,
   visited by `id`). A constraint is *observed* from a reference, not *registered*
   at construction.
2. Each cross-object constraint is an immutable data object (`Constraint`).
3. The dependency graph (edge "A references B => B resolves before A") is ordered
   with `graphlib.TopologicalSorter`.
4. Constraints are resolved bottom-up into a fresh internal context, reusing the
   *conflict/uniqueness semantics* of `species_requirements` so the new engine
   reproduces current species behaviour.
5. The `pypicongpu.Simulation` tree is constructed from the resolved context by
   reusing the incumbent per-class `get_as_pypicongpu` methods (kept as the
   reference path, Q4) against the resolved copy.
"""

import graphlib
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterator

from pydantic import BaseModel

from .species import DependsOn
from .species_requirements import DelayedConstruction


class ConstraintKind(str, Enum):
    """Abstract relationship categories (issue #107 spec, section 'Categorized')."""

    ONE_TO_ONE = "one_to_one"
    HAS_PROPERTY = "has_property"
    HAS_PROPERTY_OF_VALUE = "has_property_of_value"
    ORDERING = "ordering"


@dataclass(frozen=True)
class Constraint:
    """An immutable, declarative cross-object constraint.

    This is the "re-expressed as data" form of a requirement: instead of the
    mutable, pydantic-wrapped-lambda `DelayedConstruction` machinery, a constraint
    records *what* it needs (slot, value) and *from where* (source), plus the kind
    of relationship it encodes.
    """

    kind: ConstraintKind
    slot: str
    value: Any
    source: str  # type name of the constraining object
    target: str  # type name of the object the constraint applies to
    unique: bool = False  # a "unique" slot rejects duplicates (conflict semantics)

    def conflicts_with(self, other: "Constraint") -> bool:
        """Two constraints on the same unique slot conflict unless they agree."""
        if self.slot != other.slot or not (self.unique or other.unique):
            return False
        try:
            agree = self.value == other.value
        except Exception:  # apples and oranges: treat as agreement (non-conflict)
            return False
        return not agree


class ConstraintSet:
    """Accumulator of constraints on one target, with conflict/uniqueness semantics.

    Re-expresses the *idea* of `resolving_add`/`check_for_conflict`/`must_be_unique`
    as immutable data rather than in-place mutation of lambdas: adding a
    constraint checks for conflicts, and a unique slot rejects a second,
    disagreeing constraint.
    """

    def __init__(self):
        self._by_slot: dict[str, list[Constraint]] = {}

    def add(self, constraint: Constraint) -> None:
        existing = self._by_slot.get(constraint.slot, [])
        for other in existing:
            if other.conflicts_with(constraint):
                raise ValueError(
                    f"Conflicting constraints on slot {constraint.slot!r}: "
                    f"{constraint.source} vs {other.source}."
                )
            if other.unique and self._is_same(other, constraint):
                return  # unique slot: the identical constraint is already present
        self._by_slot.setdefault(constraint.slot, []).append(constraint)

    @staticmethod
    def _is_same(a: Constraint, b: Constraint) -> bool:
        try:
            return a.kind == b.kind and a.value == b.value and a.source == b.source
        except Exception:
            return False

    def get(self, slot: str) -> list[Constraint]:
        return list(self._by_slot.get(slot, []))


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


def deep_copy(obj, seen: dict[int, BaseModel]) -> Any:
    """Pure, memoised, structure-preserving deep copy of a PICMI object graph.

    Uses `model_copy(deep=False)` plus manual recursion so that nested
    `BaseModel`s (including those buried in private attributes and in the
    `metadata` of requirement objects) are all re-copied while staying
    referentially consistent. Scalars are shared; the result is a disjoint copy
    that can be mutated without affecting the input.
    """
    if isinstance(obj, BaseModel):
        if (existing := seen.get(id(obj))) is not None:
            return existing
        new = obj.model_copy(deep=False)
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
