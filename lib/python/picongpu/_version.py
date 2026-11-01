"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

from functools import lru_cache
from picongpu import core


@lru_cache
def _parse_version():
    with (core.path("include") / "picongpu" / "version.hpp").open("r") as version_header:
        header_code = version_header.read()
    version_dict = {
        key: s.split(" ")[1].strip()
        for key, s in zip(
            ("major", "minor", "patch", "label"),
            filter(lambda s: s.startswith("PICONGPU_VERSION_"), header_code.split("\n#define ")),
        )
    }
    return _compose_version(version_dict)


def _parse_c_string_literal(value):
    # PICONGPU_VERSION_LABEL is a C string literal (e.g. "dev" or ""). Take
    # the text between the first and last quote and trim it, so surrounding
    # padding cannot leak into the version. Values without quotes (e.g. the
    # numeric fields) are returned trimmed as-is.
    value = value.strip()
    start = value.find('"')
    end = value.rfind('"')
    if start == -1 or end <= start:
        return value
    return value[start + 1 : end].strip()


def _compose_version(version_dict):
    label = _parse_c_string_literal(version_dict.get("label", ""))
    version = f"{version_dict['major']}.{version_dict['minor']}.{version_dict['patch']}"
    return version + (f"-{label}" if label else "")


__version__ = _parse_version()
