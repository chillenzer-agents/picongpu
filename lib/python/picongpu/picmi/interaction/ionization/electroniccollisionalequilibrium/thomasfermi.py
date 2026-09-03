"""
This file is part of PIConGPU.
Copyright 2024-2024 PIConGPU contributors
Authors: Brian Edward Marre
License: GPLv3+
"""

from ..... import pypicongpu
from ..groundstateionizationmodel import GroundStateIonizationModel


class ThomasFermi(GroundStateIonizationModel):
    """thomas fermi ionization model"""

    MODEL_NAME: str = "ThomasFermi"

    def get_as_pypicongpu(self) -> pypicongpu.species.constant.ionizationmodel.IonizationModel:
        self.check()

        return pypicongpu.species.constant.ionizationmodel.ThomasFermi()
