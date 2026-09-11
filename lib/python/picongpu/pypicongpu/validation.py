"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz, opencode
License: GPLv3+

Shared free-function validators for pypicongpu pydantic models.

Every function is a plain ``Callable`` that either returns its (possibly
normalised/adjusted) argument or raises a ``ValueError`` with an actionable
message. They can be used directly as pydantic ``AfterValidator`` /
``BeforeValidator`` or invoked inside a ``field_validator`` / ``model_validator``.

The helpers are importable from the PICMI layer as well (PICMI already depends
on pypicongpu), so duplicated validation lives in exactly one place.
"""

import math
import re

from .vector import deserialise_vec

_CPP_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_CPP_IDENTIFIER_WITH_PREFIX = re.compile(r"^[A-Za-z0-9_]+$")


def validate_cpp_identifier(value: str, *, field: str = "name", prefix: str = "") -> str:
    """Validate that a string is a valid C++ identifier.

    Strings that are rendered verbatim into generated C++ names must be valid
    C++ identifiers. If ``prefix`` is given, the value is considered in the
    context of ``prefix + value`` (e.g. ``prefix="species_"`` allows a leading
    digit because the rendered identifier starts with a letter).
    """
    pattern = _CPP_IDENTIFIER_WITH_PREFIX if prefix else _CPP_IDENTIFIER
    if not pattern.fullmatch(value):
        if prefix:
            raise ValueError(
                f"{field} must be a valid C++ identifier when prefixed with {prefix!r} "
                f"(allowed: [A-Za-z0-9_]+). You gave {value!r}."
            )
        raise ValueError(f"{field} must be a valid C++ identifier ([A-Za-z_][A-Za-z0-9_]*). You gave {value!r}.")
    return value


def positive(value: float, *, field: str = "value") -> float:
    """Require a strictly positive scalar."""
    if value <= 0:
        raise ValueError(f"{field} must be greater than 0. You gave: {value=}.")
    return value


def all_positive(values, *, field: str = "value"):
    """Require that every element of an iterable is strictly positive."""
    if not all(value > 0 for value in values):
        raise ValueError(f"All elements of {field} must be greater than 0. You gave: {values=}.")
    return values


def non_negative(value: float, *, field: str = "value") -> float:
    """Require a non-negative scalar."""
    if value < 0:
        raise ValueError(f"{field} must be greater than or equal to 0. You gave: {value=}.")
    return value


def less_than(lesser: float, greater: float, *, lesser_field: str, greater_field: str) -> None:
    """Require ``lesser < greater`` (strict)."""
    if lesser >= greater:
        raise ValueError(f"{lesser_field} must be smaller than {greater_field}. You gave: {lesser=} and {greater=}.")


def component_vector(value, *, field: str = "value"):
    """Normalise a 3-component vector given as list, tuple or ``{x, y, z}`` dict into a tuple.

    Raises an actionable error on malformed input (in contrast to the legacy
    ``validate_component_vector`` which silently swallowed exceptions).
    """
    try:
        return deserialise_vec(value)
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(
            f"{field} must be a 3-component vector given as list, tuple or {{x, y, z}} dict. You gave: {value=}."
        ) from error


def unit_vector(value, *, field: str = "value"):
    """Validate a component vector to have unit length (within a tolerance)."""
    vector = component_vector(value, field=field)
    if any(math.isinf(v) or math.isnan(v) for v in vector):
        raise ValueError(f"{field} must not contain infs or nans. You gave: {value=}.")
    vector_length = math.sqrt(sum(v**2 for v in vector))
    if not math.isclose(vector_length, 1.0, abs_tol=1.0e-5):
        raise ValueError(f"Expected {field} to be a unit vector but it has length {vector_length}. You gave: {value=}.")
    return vector


def in_unit_interval(values, *, field: str = "value"):
    """Require that every element of an iterable lies in the (half-open) unit interval [0, 1)."""
    if not all(0.0 <= value < 1.0 for value in values):
        raise ValueError(f"All elements of {field} must be in the interval [0, 1). You gave: {values=}.")
    return values


def as_list(value, matches, *, field: str = "value"):
    """Normalise a (potential) singleton into a list, i.e. ``x -> [x]`` if ``x`` matches ``matches``.

    Lists (or anything already list-shaped) pass through unchanged.
    """
    if isinstance(value, matches):
        return [value]
    return value


def exactly_one(is_set: dict[str, bool], *, message: str | None = None) -> None:
    """Require that exactly one of the given flags is truthy."""
    present = [name for name, value in is_set.items() if value]
    if len(present) != 1:
        raise ValueError(message or f"Exactly one of {list(is_set)} must be provided. You gave: {present=}.")


def same_length(a, b, *, a_field: str, b_field: str) -> None:
    """Require that two sequences have the same length."""
    if len(a) != len(b):
        raise ValueError(
            f"{a_field} and {b_field} must have the same length. You gave: {len(a)} entries in {a_field} and "
            f"{len(b)} entries in {b_field}."
        )


def at_least_one_of(is_set: dict[str, bool], *, message: str | None = None) -> None:
    """Require that at least one of the given flags is truthy."""
    if not any(is_set.values()):
        raise ValueError(message or f"At least one of {list(is_set)} must be provided.")


def radius_larger_than(value: float, bound: float, *, field: str = "radius_si") -> float:
    """Require ``value >= bound``, e.g. for a cylinder radius vs. its plasma ramp length."""
    if value < bound:
        raise ValueError(
            f"{field} must be >= {bound}, so that the reduced radius stays non negative. You gave: {value=}."
        )
    return value
