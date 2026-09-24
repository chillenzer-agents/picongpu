"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

from pydantic import BaseModel, PrivateAttr, model_serializer, model_validator


class UnitDimension(BaseModel):
    """
    the SI unit dimension of a particle functor's return value

    C++ counterpart: the std::array<double, 7u> unit dimension rendered
    into the binning setup (see
    include/picongpu/plugins/binning/UnitConversion.hpp).

    Units policy: the seven entries are the exponents of the SI base units
    (dimensionless), in PIConGPU order: L (length), M (mass), T (time),
    I (electric current), Theta (thermodynamic temperature), N (amount of
    substance), J (luminous intensity).
    """

    _num_unit_dimensions: int = PrivateAttr(7)
    unit_dimension: list[float] = _num_unit_dimensions.default * [0.0]
    """the seven SI base unit exponents, [dimensionless]; the vector length
    must be exactly 7 (enforced by validation)"""

    @model_validator(mode="after")
    def check(self):
        if len(self.unit_dimension) != self._num_unit_dimensions:
            raise ValueError(
                f"Unit dimension vector has {len(self.unit_dimension)=} but {self._num_unit_dimensions=}. They must match."
            )
        return self

    @model_serializer(mode="plain")
    def translate_to_cpp(self) -> str:
        return f"std::array<double, {self._num_unit_dimensions}u>{{{','.join(map(str, self.unit_dimension))}}}"
