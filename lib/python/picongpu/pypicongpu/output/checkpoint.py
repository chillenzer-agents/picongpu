"""
This file is part of PIConGPU.
Copyright 2021-2025 PIConGPU contributors
Authors: Masoud Afshari
License: GPLv3+
"""

from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

from .timestepspec import TimeStepSpec


class Checkpoint(BaseModel):
    """
    the checkpoint plugin (top level)

    C++ counterpart: the checkpoint plugin parameters
    (--checkpoint.* in etc/picongpu/N.cfg).

    At least one of `period` (time-step based) or `timePeriod` (wall-time
    based) must be provided.

    Units policy: time steps are dimensionless; `timePeriod` is a wall-time
    interval in [min].
    """

    period: TimeStepSpec | None = None
    """the time steps at which checkpoints are written, [time-step number];
    required if timePeriod is not given"""

    timePeriod: Annotated[int, Field(ge=0)] | None = None
    """wall-time interval between checkpoints, [min]; must be >= 0;
    required if period is not given"""

    directory: Path | None = None
    """directory inside simOutput to write checkpoints into
    (C++: --checkpoint.directory)"""

    file: Annotated[str, Field(min_length=1)] | None = None
    """fileset prefix for the checkpoint files (C++: --checkpoint.file);
    must not be empty (an empty prefix would be silently dropped by the
    rendering, which would hide a typo)"""

    restart: bool | None = None
    """if True, restart the simulation from the latest checkpoint
    (C++: --checkpoint.restart)"""

    tryRestart: bool | None = None
    """if True, restart from the latest checkpoint if available, else start
    from scratch (C++: --checkpoint.tryRestart)"""

    restartStep: Annotated[int, Field(ge=0)] | None = None
    """the checkpoint step to restart from, [time-step number]; must be >= 0
    (C++: --checkpoint.restart.step)"""

    restartDirectory: Path | None = None
    """directory inside simOutput containing the checkpoints to restart from
    (C++: --checkpoint.restart.directory)"""

    restartFile: Annotated[str, Field(min_length=1)] | None = None
    """fileset prefix of the checkpoints to restart from
    (C++: --checkpoint.restart.file); must not be empty"""

    restartChunkSize: Annotated[int, Field(gt=0)] | None = None
    """number of particles processed in one kernel call during restart,
    [dimensionless]; must be > 0 (C++: --checkpoint.restart.chunkSize)"""

    restartLoop: Annotated[int, Field(ge=0)] | None = None
    """number of times to restart the simulation after it finishes,
    [dimensionless]; must be >= 0 (C++: --checkpoint.restart.loop)"""

    openPMD: dict | None = None
    """openPMD settings for the checkpoints; allowed keys: `ext`, `json`,
    `backendConfig`, `infix` (C++: --checkpoint.openPMD.*)"""

    type_checkpoint: Literal[True] = True
    """tag field identifying the checkpoint plugin (discriminator)"""

    @model_validator(mode="after")
    def check(self):
        if self.period is None and self.timePeriod is None:
            raise ValueError("At least one of period or timePeriod must be provided")
        return self
