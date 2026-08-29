"""
This file is part of PIConGPU.
Copyright 2025 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

from functools import reduce
from hashlib import sha256
from os import PathLike
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated, Any, Literal

import tomli_w
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    PrivateAttr,
    ValidationError,
    field_validator,
    model_serializer,
)

from picongpu.pypicongpu.output.timestepspec import TimeStepSpec
from picongpu.pypicongpu.particle_functor.filtered_species import FilteredSpecies
from picongpu.pypicongpu.particle_functor.particle_functor import ParticleFunctor
from picongpu.pypicongpu.species.species import Species
from picongpu.pypicongpu.util import unique

NATIVE_FIELDS = ["E", "B", "J"]


class RangeSpecEntry(BaseModel):
    """
    the output range in cells for one spatial dimension

    C++ counterpart: one of the three comma-separated dimension ranges in
    the `--<plugin>.range` parameter of the openPMD backend
    (e.g. `1:10`, `42`, or empty for the full dimension).

    Units policy: cell indices (dimensionless).
    """

    data: None | int | tuple[int, int] = None
    """the range, [cell index]: None = the full dimension, a single index >= 0,
    or a (lo, hi) pair with 0 <= lo <= hi"""

    @field_validator("data")
    @classmethod
    def _validate_range_entry(cls, value):
        if isinstance(value, int):
            if value < 0:
                raise ValueError(f"cell indices must be >= 0. You gave {value}.")
        elif isinstance(value, tuple):
            lo, hi = value
            if lo < 0 or hi < 0:
                raise ValueError(f"cell indices must be >= 0. You gave {value}.")
            if lo > hi:
                raise ValueError(f"the range start must not exceed its end. You gave lo={lo}, hi={hi}.")
        return value

    @model_serializer(mode="plain")
    def _serialize(self) -> str:
        if self.data is None:
            return ""
        if isinstance(self.data, int):
            return str(self.data)
        if isinstance(self.data, tuple):
            return ":".join(map(str, self.data))
        raise ValueError(f"Can't serialize RangeSpecEntry with {self.data=}.")


class RangeSpec(BaseModel):
    """
    the output range in cells for each spatial dimension

    C++ counterpart: the `--<plugin>.range` parameter of the openPMD backend
    (e.g. `1:10,:,42:`); rendered as three comma-separated dimension ranges.

    Units policy: cell indices (dimensionless).
    """

    data: tuple[RangeSpecEntry, RangeSpecEntry, RangeSpecEntry] = (RangeSpecEntry(), RangeSpecEntry(), RangeSpecEntry())
    """exactly three entries (x, y, z); each entry is None (full dimension),
    a single cell index >= 0, or a (lo, hi) cell range"""

    @model_serializer()
    def _serialize_data(self) -> str:
        return ",".join(map(BaseModel.model_dump, self.data))


class OpenPMDConfig(BaseModel):
    """
    the openPMD backend configuration of a plugin

    C++ counterpart: the openPMD backend configuration file
    (file, infix, ext, backend_config, data_preparation_strategy, range).

    Units policy: cell indices (dimensionless).
    """

    file: PathLike | str
    """file prefix for the openPMD output (C++: file); combined with `infix`
    and `ext` into the full filename"""

    infix: str = "_%06T"
    """iteration expansion pattern between `file` and `ext` (C++: infix);
    `%T` is replaced by the zero-padded iteration"""

    ext: Annotated[str, AfterValidator(lambda s: s.strip("."))] = "bp5"
    """file extension (C++: ext); leading dots are stripped, so "h5" and
    ".h5" are equivalent"""

    backend_config: PathLike | None = None
    """path to an additional openPMD backend configuration file
    (C++: backend_config); None = none"""

    data_preparation_strategy: Literal["mappedMemory", "doubleBuffer"] = "mappedMemory"
    """how the backend prepares the output data (C++: dataPreparationStrategy)"""

    range: RangeSpec = RangeSpec()
    """output range in cells per dimension (C++: range); default = full domain"""

    @field_validator("range", mode="before")
    @classmethod
    def _validate_range(cls, value):
        try:
            return RangeSpec(data=value)
        except ValidationError as error1:
            try:
                return RangeSpec(data=map(lambda x: RangeSpecEntry(data=x), value))
            except ValidationError as error2:
                raise error2 from error1
        return value

    def full_filename(self):
        return f"{self.file}{self.infix}.{self.ext}"

    def result_path(self, prefix_path: PathLike = Path()):
        filename = self.full_filename()
        if Path(filename).is_absolute():
            return filename
        return (Path(prefix_path) / filename).absolute()


def to_string(timestepspec: TimeStepSpec):
    return ",".join(
        map(
            lambda x: "{start}:{stop}:{step}".format(**x),
            timestepspec.get_rendering_context()["specs"],
        )
    )


class FieldDump(BaseModel):
    """
    a dump of a single (derived) field into the openPMD output

    C++ counterpart: one entry of the openPMD backend sink configuration
    (the variable name, optionally with a particle filter and functor).

    Units policy: see the functor.
    """

    name: str
    """name of the field variable in the openPMD output"""

    functor: ParticleFunctor | None = None
    """the particle functor computing the derived field; None for native
    fields (E, B, J)"""

    filtername: None | str = None
    """name of the particle filter applied to the species, [C++ identifier];
    rendered as `picongpu::particles::filter::{filtername}`, so it must be a
    valid C++ identifier (it is derived from the filter functor's name)"""

    def get_rendering_context(self) -> dict:
        return self.model_dump(mode="json")


class OpenPMDPlugin(BaseModel):
    """
    the openPMD plugin (top level)

    C++ counterpart: the openPMD plugin instance (a list of
    (period, source) pairs plus the openPMD backend configuration).

    Units policy: see the sub-models.
    """

    sources: list[tuple[TimeStepSpec, Species | FieldDump | FilteredSpecies]]
    """the output sources: one (period, source) pair per dumped field,
    species, or filtered species"""

    config: OpenPMDConfig = OpenPMDConfig(file="simData")
    """the openPMD backend configuration"""

    type_openPMD: Literal[True] = True
    """tag field identifying the openPMD plugin (discriminator)"""

    _setup_dir: Path | None = PrivateAttr(None)
    # We're using a negation here because now `False` and `None` (evaluating to `False`)
    # both mean that we can't rely on `setup_dir` being anything permanent:
    _setup_dir_is_not_temporary: bool | None = PrivateAttr(None)

    def config_filename(self, content, context: Literal["runtime", "setup"]):
        filename = f"openPMD_config_{sha256(tomli_w.dumps(content).encode()).hexdigest()}.toml"
        if not self._setup_dir_is_not_temporary or context == "setup":
            return self.setup_dir / "etc" / filename
        if context == "runtime":
            return Path("..") / "input" / "etc" / filename
        raise ValueError(f"Unknown {context=} upon requesting the openPMD config filename.")

    @property
    def setup_dir(self):
        if self._setup_dir_is_not_temporary is None:
            self._setup_dir_is_not_temporary = self._setup_dir is not None

        if self._setup_dir is None:
            self._setup_dir = Path(TemporaryDirectory(delete=False).name).absolute()

        return self._setup_dir

    @setup_dir.setter
    def setup_dir(self, other):
        self._setup_dir = Path(other)

    def _generate_config_file(self):
        # There's some strange interaction with the custom hashing of TimeStepSpec
        # that's implemented on RenderedObject
        # hindering the storage of this data structure.
        # As a workaround, we're computing this on the fly.
        # Shouldn't be performance critical but it would be more elegant to normalise early on.
        sources = reduce(
            lambda dictionary, key_val: (
                dictionary.setdefault(to_string(key_val[0]), []).append(key_val[1].get_rendering_context()["name"])
                or dictionary
            ),
            self.sources,
            {},
        )
        content = self.config.model_dump(mode="json", exclude_none=True) | {
            "sink": {"dummy_application_name": {"period": sources}}
        }
        with self.config_filename(content, context="setup").open("wb") as file:
            tomli_w.dump(content, file)
        return content

    @model_serializer(mode="plain")
    def _get_serialized(self) -> dict[str, Any] | None:
        content = self._generate_config_file()
        return {
            "type_openPMD": True,
            "config_filename": str(self.config_filename(content, context="runtime")),
            "derived_fields": unique(
                source[1].model_dump(mode="json")
                for source in self.sources
                if isinstance(source[1], FieldDump) and source[1].functor is not None
            ),
        }

    model_config = ConfigDict(arbitrary_types_allowed=True)
