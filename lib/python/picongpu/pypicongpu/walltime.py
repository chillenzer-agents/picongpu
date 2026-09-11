"""
This file is part of the PIConGPU.
Copyright 2024-2025 PIConGPU contributors
Authors: Brian Edward Marre, Richard Pausch, Julian Lenz
License: GPLv3+
"""

from datetime import timedelta
from typing import Annotated

from pydantic import BaseModel, PlainSerializer, field_validator

from .rendering import RenderedObject
from .validation import positive


def serialise_timedelta(value):
    HOUR = timedelta(hours=1.0)
    MINUTE = timedelta(minutes=1.0)
    SECOND = timedelta(seconds=1.0)

    hours, rest = divmod(value, HOUR)
    minutes, rest = divmod(rest, MINUTE)
    seconds, _ = divmod(rest, SECOND)
    return "{:d}:{:02d}:{:02d}".format(hours, minutes, seconds)


class Walltime(RenderedObject, BaseModel):
    walltime: Annotated[timedelta, PlainSerializer(serialise_timedelta)]
    """time after which the cluster scheduler will stop the simulation"""

    @field_validator("walltime", mode="after")
    @classmethod
    def check(cls, value) -> None:
        positive(value.total_seconds(), field="walltime")
        return value
