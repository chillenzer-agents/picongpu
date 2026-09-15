"""
This file is part of PIConGPU.
Copyright 2024-2024 PIConGPU contributors
Authors: Brian Edward Marre
License: GPLv3+
"""

from .... import pypicongpu
from ....picmi import mutation_switch
from .ionizationmodel import IonizationModel


class GroundStateIonizationModel(IonizationModel):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # When the switch is off, `IonizationModel.__init__` already returned early,
        # so the base class did not register anything; mirror that here so the
        # model's element-properties constant is not registered eagerly either.
        if not mutation_switch.INIT_MUTATION_ENABLED:
            return
        self.ion_species.register_requirements(self.get_constants())

    def get_constants(self) -> list[pypicongpu.species.constant.Constant]:
        """get all PyPIConGPU constants required by a ground state ionization model in PIConGPU"""
        self.check()

        # the initial charge state is validated against the element by
        # pypicongpu's SetChargeState operation when the species is
        # translated.
        element_properties_const = pypicongpu.species.constant.ElementProperties(
            element=self.ion_species.picongpu_element
        )
        return [element_properties_const]
