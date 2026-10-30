"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""


def normalize_none(value):
    """
    replace every ``None`` in a rendering context by an empty string

    ``moosetash`` treats a present key whose value is ``None`` as a missing
    variable. An empty string is falsy just like ``None``, so section and
    inverted-section semantics are preserved while no spurious
    ``MissingVariable`` is raised. All other values (including ``False``,
    ``0`` and empty containers) are left untouched.

    Recurses through dictionaries, lists and tuples.

    :param value: rendering context (or any of its nested values)
    :return: copy of the context with every ``None`` replaced by ``""``
    """
    if value is None:
        return ""
    if isinstance(value, dict):
        return {key: normalize_none(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize_none(item) for item in value]
    if isinstance(value, tuple):
        return tuple(normalize_none(item) for item in value)
    return value
