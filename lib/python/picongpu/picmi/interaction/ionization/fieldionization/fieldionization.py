"""
This file is part of PIConGPU.
Copyright 2024-2024 PIConGPU contributors
Authors: Brian Edward Marre
License: GPLv3+
"""

from picmistandard.base import _PICMI_Extension

from ..groundstateionizationmodel import GroundStateIonizationModel
from .ionizationcurrent import IonizationCurrent

from .....pypicongpu.species.constant.ionizationcurrent import IonizationCurrent as PypicongpuIonizationCurrent
from .....pypicongpu.species.constant.ionizationcurrent import None_


class FieldIonization(GroundStateIonizationModel, _PICMI_Extension):
    """common interface of all field ionization models

    inheriting from ``_PICMI_Extension`` makes the concrete field ionization
    models (ADK, BSI, Keldysh) usable as PIConGPU PICMI extensions, alongside
    the standard-facing :class:`PICMI_FieldIonization`.
    """

    ionization_current: IonizationCurrent | None
    """ionization current for energy conservation of field ionization"""

    def _get_ionization_current(self) -> PypicongpuIonizationCurrent:
        """bridge the ionization current to the pypicongpu model

        None maps to the pypicongpu None_ current (the C++ default
        current::None). A concrete current is converted via its
        get_as_pypicongpu method and must result in a pypicongpu
        ionization current model; otherwise an error is raised instead of
        silently dropping the current.
        """
        if self.ionization_current is None:
            return None_()
        current = (
            self.ionization_current.get_as_pypicongpu()
            if hasattr(self.ionization_current, "get_as_pypicongpu")
            else self.ionization_current
        )
        if not isinstance(current, PypicongpuIonizationCurrent):
            raise ValueError(
                f"Unsupported ionization current {self.ionization_current!r}: it does not convert to a pypicongpu "
                "ionization current model, and silently dropping it would change the physics."
            )
        return current
