"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""


def normalize_none(value):
    """
    replace every ``None`` in a rendering context by an empty string

    This is a local stand-in for the upstream ``fix-none-handling`` engine
    build, not a byte-for-byte equivalent: that build renders an interpolated
    present ``None`` as ``"None"`` and returns ``None`` for partially-missing
    dotted names, whereas this shim yields ``""`` and a genuinely absent
    variable still raises ``MissingVariable``. Current templates only use
    these values in sections, where ``None`` and ``""`` are both falsy, so the
    difference does not affect their output.

    All other values (including ``False``, ``0`` and empty containers) are
    left untouched.

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
