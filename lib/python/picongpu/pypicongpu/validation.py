"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+

Shared free-function validators for pypicongpu pydantic models.
"""

import re

_CPP_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_CPP_IDENTIFIER_WITH_PREFIX = re.compile(r"^[A-Za-z0-9_]+$")


def validate_cpp_identifier(value: str, *, field: str = "name", prefix: str = "") -> str:
    """Validate that a string is a valid C++ identifier.

    If ``prefix`` is given, the value is considered in the context of
    ``prefix + value`` (e.g. prefix="species_" allows a leading digit because
    the rendered identifier starts with a letter).
    """
    pattern = _CPP_IDENTIFIER_WITH_PREFIX if prefix else _CPP_IDENTIFIER
    if not pattern.fullmatch(value):
        if prefix:
            raise ValueError(
                f"{field} must be a valid C++ identifier when prefixed with {prefix!r} "
                f"(allowed: [A-Za-z0-9_]+). You gave {value!r}."
            )
        raise ValueError(f"{field} must be a valid C++ identifier ([A-Za-z_][A-Za-z0-9_]*). You gave {value!r}.")
    return value
