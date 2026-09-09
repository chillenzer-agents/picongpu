"""
This file is part of PIConGPU.
Copyright 2024-2024 PIConGPU contributors
Authors: Brian Edward Marre
License: GPLv3+
"""

from ..groundstateionizationmodel import GroundStateIonizationModel
from ..... import pypicongpu


class ThomasFermi(GroundStateIonizationModel):
    """thomas fermi ionization model"""

    MODEL_NAME: str = "ThomasFermi"

    def get_as_pypicongpu(self) -> pypicongpu.species.constant.ionizationmodel.IonizationModel:
        self.check()

        # the C++ ThomasFermi ionizer is parameterised by the electron species
        # to be created (T_DestSpecies)
        return pypicongpu.species.constant.ionizationmodel.ThomasFermi(
            ionization_electron_species=self.ionization_electron_species.get_as_pypicongpu()
        )
