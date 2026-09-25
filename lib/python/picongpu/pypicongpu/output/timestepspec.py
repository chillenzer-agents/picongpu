"""
This file is part of PIConGPU.
Copyright 2025 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

from typing import Annotated
from pydantic import BaseModel, Field, PlainSerializer, field_validator
from ..rendering.renderedobject import RenderedObject


class Spec(BaseModel):
    """
    a single (start, stop, step) output period

    Rendered as `start:stop:step` into the plugin period arguments
    (e.g. --checkpoint.period in etc/picongpu/N.cfg).

    Units policy: time-step numbers (dimensionless); stop = -1 means
    "until the end of the simulation".
    """

    start: Annotated[int | None, Field(ge=0), PlainSerializer(lambda x: x if x is not None else 0)]
    """first time step of the period, [time-step number]; must be >= 0 (None = 0)."""

    stop: Annotated[int | None, Field(ge=-1), PlainSerializer(lambda x: x if x is not None else -1)]
    """last time step of the period (inclusive), [time-step number]; must be >= -1,
    where -1 means "until the end of the simulation" (None = -1)."""

    step: Annotated[int | None, Field(ge=1), PlainSerializer(lambda x: x if x is not None else 1)]
    """period between consecutive outputs, [time-step number]; must be >= 1 (None = 1).

    Note: no start <= stop invariant is enforced (not even as a warning): the
    PICMI slice semantics deliberately allow start > stop (such a spec selects
    an empty set of time steps) and the test suite runs such specs through the
    conversion with warnings-as-errors enabled."""


class TimeStepSpec(RenderedObject, BaseModel):
    """
    a set of (start, stop, step) output periods (union of the periods)

    C++ counterpart: the `--<plugin>.period` arguments in
    etc/picongpu/N.cfg (one comma-separated start:stop:step entry per spec).

    Units policy: time-step numbers (dimensionless).
    """

    specs: list[Spec]
    """the output periods; each spec satisfies start >= 0, stop >= -1 and step >= 1"""

    def __init__(self, *args, **kwargs):
        # allow to give specs as positional argument
        if len(args) > 0 and "specs" not in kwargs:
            kwargs |= {"specs": args[0]}
        super(TimeStepSpec, self).__init__(*args[1:], **kwargs)

    @field_validator("specs", mode="before")
    @classmethod
    def validate_specs(cls, value) -> list[Spec]:
        try:
            return [Spec(start=s.start, stop=s.stop, step=s.step) for s in value]
        except AttributeError:
            return value
