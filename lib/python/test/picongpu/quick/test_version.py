"""
Tests that the Python package version is coherent across its sources.

This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

import importlib
import importlib.metadata
import tomllib
from pathlib import Path

import pytest
from packaging.version import Version

import picongpu
from picongpu import core

PYPROJECT = Path(__file__).resolve().parents[3] / "pyproject.toml"


def _version_header_composition() -> str:
    """Compose the version from version.hpp as human-readable ``X.Y.Z[-LABEL]``."""
    header = (core.path("include") / "picongpu" / "version.hpp").read_text()
    values = {}
    for line in header.splitlines():
        line = line.strip()
        if not line.startswith("#define PICONGPU_VERSION_"):
            continue
        _, key, value = line.split(maxsplit=2)
        values[key.removeprefix("PICONGPU_VERSION_")] = value.strip()
    label = values.get("LABEL", "").strip('"')
    version = f"{values['MAJOR']}.{values['MINOR']}.{values['PATCH']}"
    return version + (f"-{label}" if label else "")


def test_version_is_valid_pep440():
    Version(picongpu.__version__)


def test_version_matches_distribution_metadata():
    try:
        distribution_version = importlib.metadata.version("picongpu")
    except importlib.metadata.PackageNotFoundError:
        pytest.skip("the picongpu distribution is not installed")
    assert Version(picongpu.__version__) == Version(distribution_version)


def test_version_matches_version_header():
    assert picongpu.__version__ == _version_header_composition()


def test_version_header_matches_pyproject():
    if not PYPROJECT.is_file():
        pytest.skip(f"no source pyproject.toml at {PYPROJECT}")
    with PYPROJECT.open("rb") as pyproject_file:
        pyproject = tomllib.load(pyproject_file)
    assert Version(_version_header_composition()) == Version(pyproject["project"]["version"])


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ('"dev"', "1.2.3-dev"),
        ("dev", "1.2.3-dev"),
        ('""', "1.2.3"),
        ('  ""  ', "1.2.3"),
        (' "dev" ', "1.2.3-dev"),
        ('" dev "', "1.2.3-dev"),
    ],
)
def test_compose_version_parses_label(label, expected):
    from picongpu._version import _compose_version

    assert _compose_version({"major": "1", "minor": "2", "patch": "3", "label": label}) == expected


def test_empty_label_in_header_has_no_trailing_dash(tmp_path, monkeypatch):
    from picongpu import _version

    header = tmp_path / "include" / "picongpu" / "version.hpp"
    header.parent.mkdir(parents=True)
    header.write_text(
        "/* synthetic version header */\n"
        "#define PICONGPU_VERSION_MAJOR 1\n"
        "#define PICONGPU_VERSION_MINOR 2\n"
        "#define PICONGPU_VERSION_PATCH 3\n"
        '#define PICONGPU_VERSION_LABEL ""\n'
    )
    monkeypatch.setattr(_version.core, "path", lambda subdir: tmp_path / subdir)
    _version._parse_version.cache_clear()
    try:
        # __version__ is computed at import time, so re-execute the module to
        # exercise _parse_version through the full header path.
        importlib.reload(_version)
        assert _version.__version__ == "1.2.3"
    finally:
        monkeypatch.undo()
        _version._parse_version.cache_clear()
        importlib.reload(_version)
