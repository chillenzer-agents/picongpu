"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+

The hybrid render projection.

``model_dump()`` is the clean, lossless, deserialisable canonical form. The
rendering context (what the Mustache templates consume) is a *projection* of
that canonical form. Most models' canonical form already is a valid render
context, so the projection is the identity; a small number of models need a
minor adjustment, and a single object (the openPMD plugin) needs a full custom
projection.

This module provides the "minor adjustment" tier of that hybrid: the
``render_converts_to`` class decorator declares a ``render_context()`` method
that derives the render context from the clean ``model_dump(mode="json")`` by
renaming, transforming, or omitting a small number of fields. It is the
render-context analogue of the PICMI ``converts_to`` idiom
(``picmi/copy_attributes.py``). For objects whose serialisation has no
correlation with the render context, override ``render_context()`` directly
(the "full custom" tier) instead of using this decorator.
"""

from typing import Any, Callable


def render_converts_to(conversions: dict[str, str | Callable] | None = None, drop: tuple[str, ...] = ()) -> Callable:
    """
    Class decorator: declare a render_context() that is a minor adjustment of
    the clean canonical serialisation (``model_dump(mode="json")``).

    ``conversions`` maps a render-context key to either
      - a ``str``: the clean-dump key to rename (``render_key = clean[source_key]``), or
      - a callable: ``render_key = callable(self, clean)`` where ``clean`` is the
        clean ``model_dump(mode="json")`` dict.

    ``drop`` names clean-dump keys to omit from the render context.

    Keys not mentioned in either ``conversions`` or ``drop`` pass through from
    the clean dump unchanged.
    """
    drop = set(drop)

    def decorator(cls):
        def render_context(self) -> dict | None:
            clean: dict[str, Any] = self.model_dump(mode="json")
            context = {key: value for key, value in clean.items() if key not in drop}
            for render_key, source in (conversions or {}).items():
                if isinstance(source, str):
                    context[render_key] = clean[source]
                else:
                    context[render_key] = source(self, clean)
            return context

        cls.render_context = render_context
        return cls

    return decorator
