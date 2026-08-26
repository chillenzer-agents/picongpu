"""
SPDX-FileCopyrightText: 2024-2024 PIConGPU contributors, Brian Edward Marre
SPDX-License-Identifier: GPL-3.0-or-later
"""

from .fieldionization import FieldIonization

from .....pypicongpu.species.constant import ionizationmodel


class Keldysh(FieldIonization):
    """Barrier Suppression Ioniztion model"""

    MODEL_NAME: str = "Keldysh"

    def get_as_pypicongpu(self) -> ionizationmodel.IonizationModel:
        self.check()

        return ionizationmodel.Keldysh(
            ionization_current=self._get_ionization_current(),
            ionization_electron_species=self.ionization_electron_species.get_as_pypicongpu(),
        )
