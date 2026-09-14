"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Brian Edward Marre
License: GPLv3+
"""

from picmistandard import PICMI_FieldIonization as _PICMIStandardFieldIonization

from .ADK import ADK
from .BSI import BSI
from .keldysh import Keldysh


# The concrete field ionization models, keyed by their lower-cased MODEL_NAME
# so the standard `model` string can be matched case-insensitively. Only field
# ionization models are exposed here; electronic-collisional-equilibrium models
# (e.g. ThomasFermi) belong to a different group and are not part of the
# standard field ionization interface.
_FIELD_IONIZATION_MODELS = {
    model.model_fields["MODEL_NAME"].default.lower(): model for model in (ADK, BSI, Keldysh)
}


class PICMI_FieldIonization(_PICMIStandardFieldIonization):
    """
    PIConGPU implementation of the PICMI standard field ionization interface.

    This is a thin, standard-compatible adapter. It carries the standard
    arguments (`model`, `ionized_species`, `product_species`) together with the
    PIConGPU-specific knobs (`ionization_current`, `ADK_variant`,
    `BSI_extensions`) and converts to one of PIConGPU's concrete field
    ionization models (`ADK`, `BSI`, `Keldysh`) at add time.

    `model` is matched case-insensitively against the concrete models'
    `MODEL_NAME` (e.g. "adk", "Adk" and "ADK" all select the ADK model). A bare
    standard field ionization uses `ionization_current=None` (the C++
    `current::None` default); the energy-conserving current remains a
    PIConGPU-specific opt-in.

    Model-specific knobs are required rather than defaulted: the ADK model
    requires `ADK_variant` and the BSI model requires `BSI_extensions`.
    """

    def __init__(self, model, ionized_species, product_species, **kw):
        # Pull the PIConGPU-specific knobs out of **kw before the standard
        # handle_init() rejects them as unexpected keyword arguments.
        self.ionization_current = kw.pop("ionization_current", None)
        self.ADK_variant = kw.pop("ADK_variant", None)
        self.BSI_extensions = kw.pop("BSI_extensions", None)
        super().__init__(model, ionized_species, product_species, **kw)

    def get_concrete(self):
        """
        Convert this standard-facing field ionization to PIConGPU's concrete
        model, returning an `ADK`, `BSI` or `Keldysh` instance that plugs into
        the existing `picongpu_interaction` pipeline.
        """
        model_class = self._resolve_model_class()
        common = dict(
            ionization_current=self.ionization_current,
            ion_species=self.ionized_species,
            ionization_electron_species=self.product_species,
        )

        if model_class is ADK:
            if self.ADK_variant is None:
                raise ValueError(
                    "ADK field ionization requires an ADK_variant. "
                    "Please provide it via ADK_variant=... "
                    "(e.g. ADK_variant=ADKVariant.LinearPolarization)."
                )
            return model_class(ADK_variant=self.ADK_variant, **common)

        if model_class is BSI:
            if self.BSI_extensions is None:
                raise ValueError(
                    "BSI field ionization requires BSI_extensions. "
                    "Please provide them via BSI_extensions=... "
                    "(e.g. BSI_extensions=[BSIExtension.StarkShift])."
                )
            return model_class(BSI_extensions=self.BSI_extensions, **common)

        # Keldysh has no model-specific knobs.
        return model_class(**common)

    def _resolve_model_class(self):
        model_name = (self.model or "").strip().lower()
        try:
            return _FIELD_IONIZATION_MODELS[model_name]
        except KeyError:
            supported = ", ".join(model.model_fields["MODEL_NAME"].default for model in (ADK, BSI, Keldysh))
            raise ValueError(
                f"Unsupported field ionization model {self.model!r}. Supported models: {supported}."
            ) from None
