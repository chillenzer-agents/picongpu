"""
This file is part of PIConGPU.
Copyright 2025 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+

Typed model of the full openPMD backend configuration schema.

This mirrors the JSON/TOML configuration understood by the openPMD API,
documented at https://openpmd-api.readthedocs.io/en/latest/details/backendconfig.html,
and pinned to openPMD-api 0.17+ (PIConGPU's CMake requires ``find_package(openPMD 0.17 ...)``,
and upstream openPMD-api is 0.18.0). The schema is organised as:

* a backend-independent root (``backend``, ``iteration_encoding``, lazy-parsing hints, ...),
* per-backend tables (``adios2``, ``hdf5``, ``json``, ``toml``), each with a
  ``dataset`` configuration that may be either a single default configuration or a
  list of pattern-matched ``{select, cfg}`` alternatives (first match wins; the entry
  without ``select`` is the default),
* nested sub-models for the ADIOS2 engine/operators, the HDF5 VFD/permanent filters and
  the JSON/TOML dataset/attribute modes.

Every leaf is ``None``-optional; serialising with ``model_dump(mode="json")`` (see the
``model_serializer`` on :class:`OpenPMDBackendConfig`) emits only the keys that were
explicitly set, so unset options stay absent and fall back to openPMD's own defaults.
This is the shared model used at the PICMI level for every openPMD-writing diagnostic
that writes through the toml ``pluginConfig`` (field dump, particle dump, binning).

All models reject unknown keys (``extra="forbid"``) so a typo becomes a clear validation
error instead of being silently dropped before openPMD ever sees it.
"""

import warnings
from typing import Any, Generic, List, Literal, Optional, TypeVar, Union

from pydantic import BaseModel, ConfigDict, model_serializer, model_validator

T = TypeVar("T")


class _OpenPMDModel(BaseModel):
    """Base for every model in the schema: reject unknown/typo keys."""

    model_config = ConfigDict(extra="forbid")


def _strip_unset(value: Any) -> Any:
    """Recursively drop ``None`` values and empty sub-model dicts, keeping meaningful
    empty lists (e.g. ``operators = []`` which disables compression for a dataset) and
    an explicitly-provided empty ``cfg`` (which openPMD requires to be present in every
    pattern-matched dataset entry)."""
    if isinstance(value, dict):
        stripped = {}
        for key, item in value.items():
            if item is None:
                continue
            item = _strip_unset(item)
            if isinstance(item, dict) and not item and key != "cfg":
                continue
            stripped[key] = item
        return stripped
    if isinstance(value, list):
        return [_strip_unset(item) for item in value if item is not None]
    return value


# --------------------------------------------------------------------------- #
# ADIOS2
# --------------------------------------------------------------------------- #
class Adios2Engine(_OpenPMDModel):
    type: Optional[str] = None
    pretend_engine: Optional[str] = None
    access_mode: Optional[Literal["Write", "Read", "Append", "ReadRandomAccess"]] = None
    # Opaque engine parameters forwarded verbatim to ``adios2::IO::SetParameters``;
    # openPMD coerces string/number/boolean values via ``asStringDynamic``.
    parameters: Optional[dict[str, Any]] = None
    # openPMD also accepts the ``<value>_override`` variants (``disk_override``,
    # ``buffer_override``, ``new_step_override``) which take precedence over the
    # non-suffixed values on a per-``flush()`` basis.
    preferred_flush_target: Optional[
        Literal["disk", "buffer", "new_step", "disk_override", "buffer_override", "new_step_override"]
    ] = None


class Adios2Operator(_OpenPMDModel):
    type: Optional[str] = None
    parameters: Optional[dict[str, Any]] = None


class Adios2Dataset(_OpenPMDModel):
    operators: Optional[Union[Adios2Operator, List[Adios2Operator]]] = None


class Adios2Config(_OpenPMDModel):
    engine: Optional[Adios2Engine] = None
    dataset: Optional[Union[Adios2Dataset, List["DatasetOverride[Adios2Dataset]"]]] = None
    use_span_based_put: Optional[bool] = None
    attribute_writing_ranks: Optional[Union[int, List[int]]] = None
    # openPMD honours ``dont_warn_unused_keys`` at any (backend) node, and the
    # documented examples place it inside a backend table.
    dont_warn_unused_keys: Optional[List[str]] = None


# --------------------------------------------------------------------------- #
# HDF5
# --------------------------------------------------------------------------- #
class Hdf5FilterZlib(_OpenPMDModel):
    type: Literal["zlib"] = "zlib"
    aggression: Optional[int] = None


class Hdf5FilterById(_OpenPMDModel):
    id: Union[int, Literal["deflate", "shuffle", "fletcher32", "szip", "nbit", "scaleoffset"]]
    type: Optional[Literal["by_id"]] = None
    flags: Optional[Literal["mandatory", "optional"]] = None
    cd_values: Optional[List[int]] = None


Hdf5Filter = Union[Hdf5FilterZlib, Hdf5FilterById]


class Hdf5Dataset(_OpenPMDModel):
    chunks: Optional[Union[Literal["auto", "none"], List[int]]] = None
    permanent_filters: Optional[Union[Hdf5Filter, List[Hdf5Filter]]] = None


class Hdf5Vfd(_OpenPMDModel):
    type: Optional[Literal["default", "subfiling"]] = None
    ioc_selection: Optional[Literal["one_per_node", "every_nth_rank", "with_config", "total"]] = None
    stripe_size: Optional[int] = None
    stripe_count: Optional[int] = None


class Hdf5Config(_OpenPMDModel):
    dataset: Optional[Union[Hdf5Dataset, List["DatasetOverride[Hdf5Dataset]"]]] = None
    vfd: Optional[Hdf5Vfd] = None
    independent_stores: Optional[bool] = None
    dont_warn_unused_keys: Optional[List[str]] = None


# --------------------------------------------------------------------------- #
# JSON / TOML
# --------------------------------------------------------------------------- #
class JsonTomlDataset(_OpenPMDModel):
    mode: Optional[Literal["dataset", "template"]] = None


class JsonTomlAttribute(_OpenPMDModel):
    mode: Optional[Literal["long", "short"]] = None


class JsonTomlConfig(_OpenPMDModel):
    dataset: Optional[JsonTomlDataset] = None
    attribute: Optional[JsonTomlAttribute] = None
    dont_warn_unused_keys: Optional[List[str]] = None


# --------------------------------------------------------------------------- #
# Per-dataset (pattern-matched) overrides
# --------------------------------------------------------------------------- #
class DatasetOverride(_OpenPMDModel, Generic[T]):
    """One entry of a pattern-matched ``<backend>.dataset`` list.

    ``select`` is an egrep regex (or a list of them); the entry without ``select`` is the
    default configuration. The first matching entry (top-down) wins.

    ``cfg`` is required by openPMD's ``JSONMatcher::readPattern``: every entry -- including
    the default entry without ``select`` -- must carry a ``cfg`` key, which may be an empty
    table (``cfg = {}``) to accept the backend defaults.
    """

    select: Optional[Union[str, List[str]]] = None
    cfg: T


# --------------------------------------------------------------------------- #
# Root / backend-independent configuration
# --------------------------------------------------------------------------- #
# The canonical openPMD key ``json`` (the JSON backend table) shadows pydantic's
# deprecated ``BaseModel.json`` compat method, which emits a ``UserWarning`` at class
# definition time. The field name is required by the openPMD schema, so we suppress the
# one-off import-time warning rather than rename the key.
with warnings.catch_warnings():
    warnings.simplefilter("ignore", category=UserWarning)

    class OpenPMDBackendConfig(_OpenPMDModel):
        backend: Optional[Literal["hdf5", "adios2", "json", "toml"]] = None
        iteration_encoding: Optional[Literal["file_based", "group_based", "variable_based"]] = None
        defer_iteration_parsing: Optional[bool] = None
        hint_lazy_parsing_timeout: Optional[int] = None
        verify_homogeneous_extents: Optional[bool] = None
        # A string method description, not a bool: openPMD reads it via
        # ``getJsonOptionLowerCase`` and maps it in
        # ``host_info::methodFromStringDescription`` (see ``ChunkInfo.cpp``).
        # A bool is coerced to ``"1"`` and then rejected with
        # ``Wrong value for JSON option 'rank_table': '1'``.
        rank_table: Optional[Literal["hostname", "mpi_processor_name", "posix_hostname"]] = None
        dont_warn_unused_keys: Optional[List[str]] = None
        adios2: Optional[Adios2Config] = None
        hdf5: Optional[Hdf5Config] = None
        json: Optional[JsonTomlConfig] = None
        toml: Optional[JsonTomlConfig] = None

        @model_validator(mode="before")
        @classmethod
        def _reject_resizable(cls, data: Any) -> Any:
            """``resizable`` is intentionally not modelled here.

            openPMD reads it only from the per-``Dataset`` constructor options
            (``HDF5IOHandler::parse_dataset_config`` reads ``config["resizable"]`` where
            ``config`` is the per-dataset config); in a Series-constructor JSON/TOML
            config the key reaches the backend only through ``hdf5.dataset`` pattern
            matching, which never forwards it to that path, so a top-level ``resizable``
            is silently ignored. Reject it with a clear message instead of shipping a
            no-op knob.
            """
            if isinstance(data, dict) and "resizable" in data:
                raise ValueError(
                    "'resizable' cannot be configured through the openPMD Series backend "
                    "config: openPMD only honours it as a per-Dataset constructor option, "
                    "so a config-level key is silently ignored. Pass it via openPMD's "
                    "Dataset options instead."
                )
            return data

        @model_serializer(mode="wrap")
        def _serialize_stripped(self, handler):
            return _strip_unset(handler(self))
