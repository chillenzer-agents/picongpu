"""
This file is part of PIConGPU.
Copyright 2025 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+

PIConGPU per-species particle boundaries.

PIConGPU's particle boundaries are per-species command-line options
(``--<species>_boundary``, ``--<species>_boundaryOffset``,
``--<species>_boundaryTemperature``; see ``include/picongpu/simulation/stage/
ParticleBoundaries.x.cpp`` and ``include/picongpu/particles/boundary/Kind.hpp``).
There is no standard equivalent, so this is a PIConGPU extension.

Semantics (grid-as-default, species-as-override):

- The grid's particle boundary conditions
  (``Cartesian3DGrid.picongpu_particle_boundary_conditions``) are the **default**
  for every species, resolved per axis (unset values inherit the field BCs).
- A species' ``picongpu_particle_boundary`` (this module's
  :class:`ParticleBoundary`) **overrides** the grid's per-axis value. If a species
  does not set it, the grid's per-axis particle BC applies.

The C++ core (``ParticleBoundaries.x.cpp``) derives each axis' *base* particle kind
from the field boundary (the ``--periodic`` flag): field periodic -> Periodic, field
open -> Absorbing, and then rejects a species' per-axis kind that is not compatible
with that base. So:

- field periodic  -> the only compatible particle kind is ``periodic``;
- field open      -> the compatible kinds are ``absorbing``, ``reflect``, ``thermal``
  (so ``reflect``/``thermal`` are only usable where the field boundary is absorbing);
- a ``periodic`` particle kind always requires a 0 offset.

:func:`resolve_species_particle_boundary` applies these rules at translation time so
we never emit a configuration the C++ binary would reject.
"""

from typing import Sequence

from pydantic import BaseModel, field_validator

from picongpu.pypicongpu import grid as pypicongpu_grid
from picongpu.pypicongpu.species.species_boundary import (
    SpeciesParticleBoundary as ResolvedSpeciesParticleBoundary,
)

from .grid import PICONGPU_BOUNDARY_CONDITION_BY_PICMI_ID, PICONGPU_PARTICLE_BOUNDARY_CONDITION_BY_PICMI_ID

# PICMI particle-boundary names accepted on the (user-facing) species field. The
# values are the PICMI-standard names; they map to the PIConGPU C++ tokens via
# PICONGPU_PARTICLE_BOUNDARY_CONDITION_BY_PICMI_ID at translation time.
_PARTICLE_BC_NAMES = frozenset(PICONGPU_PARTICLE_BOUNDARY_CONDITION_BY_PICMI_ID)
_AXES = "xyz"


class ParticleBoundary(BaseModel):
    """PIConGPU per-species particle boundary (a PIConGPU extension).

    ``boundary`` holds the per-axis kind
    (``periodic``/``absorbing``/``reflect``/``thermal``); give a single name to apply
    it on all axes or a 3-tuple for a per-axis value. ``boundary_offset`` (int, >= 0)
    is the inward offset (scalar or 3-tuple). ``boundary_temperature`` (float, >= 0,
    keV) is the temperature (scalar or 3-tuple; only affects thermal boundaries).
    """

    boundary: tuple[str, str, str]
    """per-axis particle boundary kind (PICMI names)"""

    boundary_offset: int | tuple[int, int, int] | None = None
    """per-axis inward offset (>= 0); scalar or 3-tuple; 0 for periodic axes"""

    boundary_temperature: float | tuple[float, float, float] | None = None
    """per-axis temperature in keV (>= 0); scalar or 3-tuple; only affects thermal boundaries"""

    @field_validator("boundary", mode="before")
    @classmethod
    def _normalise_boundary(cls, value):
        if isinstance(value, str):
            value = (value, value, value)
        value = tuple(value)
        if len(value) != 3:
            raise ValueError(f"boundary must be a name or a 3-element sequence (x, y, z). You gave {value!r}.")
        for i, kind in enumerate(value):
            if kind not in _PARTICLE_BC_NAMES:
                raise ValueError(
                    f"Unsupported particle boundary condition {kind!r} on axis {_AXES[i]}. "
                    f"Supported: {', '.join(sorted(_PARTICLE_BC_NAMES))}."
                )
        return value

    @field_validator("boundary_offset", "boundary_temperature", mode="before")
    @classmethod
    def _normalise_per_axis(cls, value):
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return (value, value, value)
        value = tuple(value)
        if len(value) != 3:
            raise ValueError("must be a scalar or a 3-element sequence (x, y, z)")
        return value

    @field_validator("boundary_offset")
    @classmethod
    def _offset_non_negative(cls, value):
        if value is not None and any(x < 0 for x in value):
            raise ValueError("boundary_offset must be >= 0")
        return value

    @field_validator("boundary_temperature")
    @classmethod
    def _temperature_non_negative(cls, value):
        if value is not None and any(x < 0 for x in value):
            raise ValueError("boundary_temperature must be >= 0")
        return value


def resolve_species_particle_boundary(
    name: str,
    field_boundary_conditions: Sequence[str],
    grid_particle_boundary_conditions: Sequence[str],
    override: ParticleBoundary | None,
) -> ResolvedSpeciesParticleBoundary:
    """Resolve the (grid default combined with species override) particle boundary for a species.

    :param name: species name (for error messages)
    :param field_boundary_conditions: the grid's per-axis **field** BC (PICMI names)
    :param grid_particle_boundary_conditions: the grid's resolved per-axis **particle** BC (PICMI names)
    :param override: the species' optional :class:`ParticleBoundary`, or None to use the grid default
    """
    # Whether the *field* boundary on each axis is absorbing (i.e. `--periodic 0`).
    # The C++ core sets the base particle kind from this: field periodic -> Periodic,
    # field open -> Absorbing.
    base_absorbing = [
        PICONGPU_BOUNDARY_CONDITION_BY_PICMI_ID[b] == pypicongpu_grid.BoundaryCondition.ABSORBING
        for b in field_boundary_conditions
    ]

    if override is None:
        # Grid default: the resolved grid particle BC (already per-axis PICMI names).
        tokens = [PICONGPU_PARTICLE_BOUNDARY_CONDITION_BY_PICMI_ID[b] for b in grid_particle_boundary_conditions]
        offset = None
        temperature = None
    else:
        tokens = [PICONGPU_PARTICLE_BOUNDARY_CONDITION_BY_PICMI_ID[k] for k in override.boundary]
        offset = override.boundary_offset
        temperature = override.boundary_temperature

    _check_constraints(name, tokens, base_absorbing, field_boundary_conditions, offset)

    offset_str = " ".join(str(int(x)) for x in offset) if (offset and any(x != 0 for x in offset)) else None
    temperature_str = (
        " ".join(_fmt_number(x) for x in temperature) if (temperature and any(x != 0 for x in temperature)) else None
    )

    return ResolvedSpeciesParticleBoundary(
        boundary=" ".join(tokens),
        offset=offset_str,
        temperature=temperature_str,
    )


def _check_constraints(name, tokens, base_absorbing, field_boundary_conditions, offset):
    """Enforce the C++ core's compatibility rules (see the module docstring)."""
    for axis in range(3):
        token = tokens[axis]
        absorbing = base_absorbing[axis]
        field_bc = field_boundary_conditions[axis]

        if absorbing:
            # field open -> the base kind is Absorbing; only absorbing/reflecting/
            # thermal are compatible (not periodic).
            if token == "periodic":
                raise ValueError(
                    f"Species {name}: particle boundary kind 'periodic' on axis {_AXES[axis]} is not compatible "
                    f"with the field boundary '{field_bc}' on that axis (a periodic particle boundary needs a "
                    "periodic field boundary)."
                )
        else:
            # field periodic -> the base kind is Periodic; only periodic is
            # compatible (not absorbing/reflecting/thermal).
            if token != "periodic":
                raise ValueError(
                    f"Species {name}: particle boundary kind '{token}' on axis {_AXES[axis]} is not compatible "
                    f"with the field boundary '{field_bc}' on that axis (only 'periodic' is compatible with a "
                    "periodic field boundary)."
                )

        off = offset[axis] if offset else 0
        if token == "periodic" and off != 0:
            raise ValueError(
                f"Species {name}: periodic particle boundary on axis {_AXES[axis]} requires a 0 offset, you gave {off}."
            )


def _fmt_number(x) -> str:
    return str(int(x)) if float(x) == int(x) else str(x)
