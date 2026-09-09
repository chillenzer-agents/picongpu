"""
This file is part of PIConGPU.
Copyright 2021-2024 PIConGPU contributors
Authors: Hannes Troepgen, Brian Edward Marre
License: GPLv3+
"""

from pydantic import BaseModel, computed_field, field_validator, model_validator
from enum import Enum

from picongpu.pypicongpu.species.constant.synchrotron import SynchrotronConstant
from picongpu.pypicongpu.validation import validate_cpp_identifier

from ..rendering import RenderedObject
from .attribute import Attribute, BoundElectrons, Momentum, Position, Weighting
from .attribute.momentum_prev_1 import MomentumPrev1
from .attribute.radiation_mask import RadiationMask
from .constant import (
    Charge,
    Constant,
    DensityRatio,
    ElementProperties,
    GroundStateIonization,
    Mass,
)


class Shape(Enum):
    """particle shape (charge/current deposition scheme) of a species

    The values are rendered verbatim as `particles::shapes::<value>` in
    speciesDefinition.param, so each value must stay a valid C++ identifier
    (e.g. shapes/TSC.hpp, shapes/Counter.hpp). The member names are the
    Python-level PICMI shape identifiers.
    """

    NGP = "NGP"
    linear = "CIC"
    quadratic = "TSC"
    cubic = "PQS"
    quartic = "PCS"
    counter = "Counter"


class Pusher(Enum):
    """particle pusher (equation of motion integrator) of a species

    The member names mirror the C++ struct names declared in
    include/picongpu/param/pusher.param (namespace particles::pusher) and
    the values are rendered verbatim as `particles::pusher::<value>` in
    speciesDefinition.param, so both must stay valid C++ identifiers.

    Note: the `particles::pusher::Axel` struct declaration is currently
    missing in pusher.param (only the particlePusherAxel parameter namespace
    and the species.param documentation remain); using Axel therefore renders
    C++ that will not compile until the declaration is restored on the C++
    side.
    """

    # supported by standard and PIConGPU
    Boris = "Boris"
    Vay = "Vay"
    HigueraCary = "HigueraCary"
    Free = "Free"
    # not supported by standard
    ReducedLandauLifshitz = "ReducedLandauLifshitz"
    Acceleration = "Acceleration"
    Photon = "Photon"
    Probe = "Probe"
    Axel = "Axel"


class Constants(BaseModel):
    """
    the set of constants ("particle flags") of a species

    Each constant may be present at most once; the set is rendered into
    include/picongpu/param/speciesDefinition.param as the ParticleFlags.

    Units policy: see the individual constants (SI).
    """

    mass: Mass | None
    """mass of the species, [kg] (None if the species has no mass constant)"""

    charge: Charge | None
    """charge of the species, [C] (None if the species has no charge constant)"""

    density_ratio: DensityRatio | None
    """density ratio relative to the base density, [dimensionless]"""

    element_properties: ElementProperties | None
    """chemical element properties (atomic number, ionization energies)"""

    ground_state_ionization: GroundStateIonization | None
    """ground state ionization models (None if not ionizing)"""

    synchrotron: SynchrotronConstant | None
    """synchrotron radiation constant marking the photon species"""


def has_constant_of_type(constants, needle_type: type[Constant]) -> bool:
    """
    lookup if constant of given type is present

    Searches through constants of this species and returns true if a
    constant of the given type is present.

    :param needle_type: constant type to look for
    :return: whether constant of needle_type exists
    """

    constants_types = list(map(type, constants))
    return needle_type in constants_types


def get_constant_by_type(constants, needle_type: type[Constant]) -> Constant:
    """
    retrieve constant of given type, raise if not found

    Searches through constants of this species and returns the constant of
    the given type if found. If no constant of this type is found, an error
    is raised.

    :param needle_type: constant type to look for
    :raise RuntimeError: on failure to find constant of given type
    :return: constant of given type
    """
    for const in constants:
        # note: check using type equality, because polymorphy messes with
        # duplicate detection & rendering
        if needle_type is type(const):
            return const

    raise RuntimeError("no constant of requested type available: {}".format(needle_type))


# concrete attribute classes by their (default) picongpu_name, used to
# reconstruct the concrete class from the serialised form (round-trip safety)
_ATTRIBUTE_CLASSES_BY_NAME = {
    "position<position_pic>": Position,
    "weighting": Weighting,
    "momentum": Momentum,
    "boundElectrons": BoundElectrons,
    "momentumPrev1": MomentumPrev1,
    "radiationMask": RadiationMask,
}


class Species(RenderedObject, BaseModel):
    """
    PyPIConGPU species definition

    A "species" is a set of particles, which is defined by:

    - A set of species constants (mass, charge, etc.),
    - a set of species attributes (position, number of bound electrons), and
    - a set of operations which collectively initialize these attributes,
      where one attribute is initialized by exactly one operation.
    - (and a name)

    Note that some of the species attributes or constants are considered
    mandatory. Each species constant or attribute may only be defined once.

    C++ counterpart: include/picongpu/param/speciesDefinition.param
    (one particle typedef per species).

    Units policy: SI (see the individual constants/attributes).
    """

    constants: Constants
    """PIConGPU particle flags (constants of the species)"""

    attributes: list[Attribute]
    """PIConGPU particle attributes of the species; must contain position and momentum,
    each at most once"""

    pusher: Pusher = Pusher["Boris"]
    """particle pusher (equation of motion integrator)"""

    name: str
    """name of the species; must be a valid C++ identifier ([A-Za-z0-9_]+),
    it renders into the particle typedef (species_<name>) and the PMACC_CSTRING name."""

    shape: Shape = Shape("TSC")
    """particle shape (charge/current deposition scheme)"""

    @computed_field
    def species_name(self) -> str:
        return self.name

    @computed_field
    def filter_name(self) -> str:
        return "all"

    @computed_field
    def filter_typename(self) -> str:
        return "All"

    @computed_field
    def typename(self) -> str:
        """
        get (standalone) C++ name for this species
        """
        return "species_" + self.name

    def __hash__(self):
        # species must be uniquely defined by name
        return hash(self.name)

    @field_validator("name")
    @classmethod
    def _validate_name(cls, name: str) -> str:
        # The name renders into the C++ typedef `species_<name>`; the
        # "species_" prefix makes even a leading digit acceptable.
        return validate_cpp_identifier(name, field="species name", prefix="species_")

    @field_validator("attributes", mode="before")
    @classmethod
    def _reconstruct_attributes(cls, attributes):
        # reconstruct the concrete attribute class from its serialised form
        # (a dict holding the picongpu_name) so that model_dump(mode="json")
        # output can be validated again (round-trip safety); the base
        # Attribute type is not discriminable from the serialised form alone
        if isinstance(attributes, list):
            return [
                _ATTRIBUTE_CLASSES_BY_NAME[elem["picongpu_name"]](**elem)
                if isinstance(elem, dict) and elem.get("picongpu_name") in _ATTRIBUTE_CLASSES_BY_NAME
                else elem
                for elem in attributes
            ]
        return attributes

    @model_validator(mode="after")
    def _validate_attributes(self):
        # position is mandatory attribute
        if Position not in [type(a) for a in self.attributes]:
            raise ValueError("Each species must have the position attribute!")
        # momentum, @todo really necessary?, Brian Marre, 2024
        if Momentum not in [type(a) for a in self.attributes]:
            raise ValueError("Each species must have the momentum attribute!")

        # each attribute (-name) can only be used once
        attr_names = list(map(lambda attr: attr.picongpu_name, self.attributes))
        non_unique_attributes = set([c for c in attr_names if attr_names.count(c) > 1])
        if 0 != len(non_unique_attributes):
            raise ValueError(
                "attribute names must be unique per species, offending: {}".format(
                    ", ".join(map(str, non_unique_attributes))
                )
            )
        return self

    @field_validator("constants", mode="before")
    @classmethod
    def constants_context(cls, value):
        # accept the serialised form (dict of constant_name -> constant dict)
        # in addition to the native list-of-constants form, so that
        # model_dump(mode="json") output can be validated again (round-trip
        # safety); the serialised keys are exactly the Constants field names
        if isinstance(value, dict):
            return Constants(**value)

        constant_names_by_type = {
            "mass": Mass,
            "charge": Charge,
            "density_ratio": DensityRatio,
            "element_properties": ElementProperties,
            "ground_state_ionization": GroundStateIonization,
            "synchrotron": SynchrotronConstant,
        }

        constants_context = {}
        for constant_name, constant_type in constant_names_by_type.items():
            if has_constant_of_type(value, constant_type):
                constants_context[constant_name] = get_constant_by_type(value, constant_type)
            else:
                constants_context[constant_name] = None

        return Constants(**constants_context)
