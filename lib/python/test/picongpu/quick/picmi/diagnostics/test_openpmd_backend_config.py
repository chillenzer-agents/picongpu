"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
License: GPLv3+
"""

import json

import pytest
import tomli_w

from picongpu.picmi.diagnostics.binning import Binning, BinningAxis, BinningFunctor, BinSpec
from picongpu.picmi.diagnostics.timestepspec import TimeStepSpec
from picongpu.picmi.species import Species
from picongpu.pypicongpu.output.openpmd_backend import (
    Adios2Config,
    Adios2Engine,
    Adios2Operator,
    Hdf5Config,
    Hdf5Dataset,
    OpenPMDBackendConfig,
)
from picongpu.pypicongpu.output.openpmd_plugin import FieldDump, OpenPMDConfig, OpenPMDPlugin
from picongpu.pypicongpu.output.timestepspec import Spec, TimeStepSpec as PyTimeStepSpec


def _adios2_with_per_dataset_overrides() -> OpenPMDBackendConfig:
    return OpenPMDBackendConfig(
        backend="adios2",
        adios2=Adios2Config(
            engine=Adios2Engine(type="sst", parameters={"Profile": "On"}),
            dataset=[
                # default entry (no select): blosc compression by default
                {"cfg": {"operators": [Adios2Operator(type="blosc", parameters={"clevel": "1"})]}},
                # select entry: no compression for matching datasets
                {"select": [".*positionOffset.*", ".*particlePatches.*"], "cfg": {"operators": []}},
            ],
        ),
        hdf5=Hdf5Config(dataset=Hdf5Dataset(chunks="auto")),
    )


def test_backend_config_renders_nested_toml_table(tmp_path):
    """A populated backend_config renders as a nested [backend_config] TOML table
    (what the C++ specialConversions() consumes) including the per-dataset
    [[backend_config.adios2.dataset]] override list."""
    (tmp_path / "etc").mkdir()
    plugin = OpenPMDPlugin(
        sources=[
            (
                PyTimeStepSpec(specs=[Spec(start=0, stop=-1, step=1)]),
                FieldDump(name="E", functor=None, filtername=None, species_name=None),
            )
        ],
        config=OpenPMDConfig(file="simData", backend_config=_adios2_with_per_dataset_overrides()),
    )
    plugin.setup_dir = tmp_path
    content = plugin._generate_config_file()
    toml_text = tomli_w.dumps(content)

    assert "[backend_config]" in toml_text
    assert 'backend = "adios2"' in toml_text
    assert "[backend_config.adios2.engine]" in toml_text
    assert 'type = "sst"' in toml_text
    assert 'Profile = "On"' in toml_text
    assert "[[backend_config.adios2.dataset]]" in toml_text
    assert 'type = "blosc"' in toml_text
    assert "select = [" in toml_text
    # the hdf5 global dataset default is also emitted
    assert "[backend_config.hdf5.dataset]" in toml_text
    assert 'chunks = "auto"' in toml_text

    # and the nested dict the C++ layer will stringify matches the model exactly
    assert content["backend_config"] == _adios2_with_per_dataset_overrides().model_dump(mode="json")


def test_unset_backend_config_is_absent():
    """No backend_config key is emitted when it is unset (openPMD defaults apply)."""
    config = OpenPMDConfig(file="simData")
    assert "backend_config" not in config.model_dump(mode="json", exclude_none=True)


def test_explicit_empty_backend_config_is_absent():
    """An explicit-but-empty backend_config is normalised to absent (no spurious empty key)."""
    config = OpenPMDConfig(file="simData", backend_config=OpenPMDBackendConfig())
    assert config.backend_config is None
    assert "backend_config" not in config.model_dump(mode="json", exclude_none=True)


def test_empty_nested_models_are_stripped():
    """Sub-models whose leaves are all unset are dropped, but meaningful empty lists stay."""
    model = OpenPMDBackendConfig(adios2=Adios2Config(engine=Adios2Engine(), dataset=[{"cfg": {"operators": []}}]))
    dumped = model.model_dump(mode="json")
    assert "engine" not in dumped["adios2"]
    # an explicit operators=[] (disabling compression) is preserved
    assert dumped["adios2"]["dataset"] == [{"cfg": {"operators": []}}]


def _binning(backend_config):
    electron = Species(particle_type="electron")
    return Binning(
        name="electron_density",
        deposition_functor=BinningFunctor(name="weighting", functor=lambda p: p.get("weighting"), return_type="double"),
        axes=[
            BinningAxis(
                functor=BinningFunctor(name="position0", functor=lambda p: 0.0, return_type="double"),
                bin_spec=BinSpec(kind="linear", start=0, stop=1, nsteps=2),
            )
        ],
        species=electron,
        period=TimeStepSpec[:],
        openPMDBackendConfig=backend_config,
        openPMDExt="h5",
    )


def test_binning_backend_config_serialises_to_json_string():
    """Binning routes the shared model through its existing JSON-string transport
    (setOpenPMDBackendConfig), emitting the model's JSON for a populated config."""
    serialized = (
        _binning(_adios2_with_per_dataset_overrides())
        .get_as_pypicongpu(time_step_size=1.0, num_steps=1)
        .model_dump()["openPMDBackendConfig"]
    )
    assert json.loads(serialized) == _adios2_with_per_dataset_overrides().model_dump(mode="json")


def test_binning_none_backend_config_yields_no_transport():
    serialized = _binning(None).get_as_pypicongpu(time_step_size=1.0, num_steps=1).model_dump()["openPMDBackendConfig"]
    assert serialized is None


def test_binning_accepts_plain_dict():
    """The shared model also accepts a plain dict (coerced), preserving the prior call style."""
    b = _binning({"hdf5": {"dataset": {"chunks": "auto"}}})
    assert isinstance(b.openPMDBackendConfig, OpenPMDBackendConfig)
    serialized = b.get_as_pypicongpu(time_step_size=1.0, num_steps=1).model_dump()["openPMDBackendConfig"]
    assert json.loads(serialized) == {"hdf5": {"dataset": {"chunks": "auto"}}}


def test_resizable_is_a_top_level_dataset_option():
    """``resizable`` is a backend-independent option that openPMD reads as a top-level key of
    the (per-)dataset config (a sibling of ``hdf5``), *not* nested under any backend table.
    It must therefore live on the root model, not on ``Hdf5Dataset``."""
    # It is accepted at the root and renders as a top-level key ...
    model = OpenPMDBackendConfig(backend="hdf5", resizable=True, hdf5=Hdf5Config(dataset=Hdf5Dataset(chunks="auto")))
    dumped = model.model_dump(mode="json")
    assert dumped["resizable"] is True
    # ... and is NOT emitted under the hdf5 dataset table (where the C++ does not read it).
    assert "resizable" not in dumped["hdf5"]["dataset"]
    # And the (former) placement on Hdf5Dataset is gone.
    assert "resizable" not in Hdf5Dataset.model_fields


@pytest.mark.parametrize(
    "target", ["disk", "buffer", "new_step", "disk_override", "buffer_override", "new_step_override"]
)
def test_adios2_preferred_flush_target_accepts_override_variants(target):
    """openPMD's ``flushTargetFromString`` accepts the ``<value>_override`` variants, which take
    precedence over the non-suffixed values on a per-``flush()`` basis; the model must allow them."""
    assert Adios2Engine(preferred_flush_target=target).preferred_flush_target == target


def test_adios2_preferred_flush_target_rejects_unknown_value():
    with pytest.raises(Exception):
        Adios2Engine(preferred_flush_target="bogus")
