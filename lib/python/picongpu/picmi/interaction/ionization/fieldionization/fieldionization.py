"""
This file is part of PIConGPU.
Copyright 2024-2024 PIConGPU contributors
Authors: Brian Edward Marre
License: GPLv3+
"""

from picmistandard.base import PICMI_Extension

from ..groundstateionizationmodel import GroundStateIonizationModel
from .ionizationcurrent import IonizationCurrent

from .....pypicongpu.species.constant.ionizationcurrent import IonizationCurrent as PypicongpuIonizationCurrent
from .....pypicongpu.species.constant.ionizationcurrent import None_


class FieldIonization(GroundStateIonizationModel, PICMI_Extension):
    """common interface of all field ionization models

    Inheriting from ``PICMI_Extension`` marks the concrete field ionization
    models (ADK, BSI, Keldysh) as code-specific PIConGPU extensions. Note that
    ``PICMI_Extension`` is *not* a subclass of ``PICMI_Interaction``, so the
    standard ``PICMI_AnyInteraction`` union does not accept the concrete
    models; the standard-facing :class:`PICMI_FieldIonization` is the entry
    point for standard code.
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
