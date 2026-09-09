"""
This file is part of PIConGPU.
Copyright 2024-2024 PIConGPU contributors
Authors: Brian Edward Marre
License: GPLv3+
"""

from .....pypicongpu.species.constant import ionizationmodel
from .....pypicongpu.species.constant.ionizationcurrent import None_
from .fieldionization import FieldIonization


class Keldysh(FieldIonization):
    """Barrier Suppression Ioniztion model"""

    MODEL_NAME: str = "Keldysh"

    def get_as_pypicongpu(self) -> ionizationmodel.IonizationModel:
        self.check()

        return ionizationmodel.Keldysh(
            ionization_current=None_(), ionization_electron_species=self.ionization_electron_species.get_as_pypicongpu()
        )
