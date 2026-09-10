"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

from pydantic import BaseModel

from picongpu.pypicongpu.rendering.renderedobject import RenderedObject
from picongpu.pypicongpu.rendering.renderprojection import render_converts_to


def test_render_converts_to_renames_transforms_and_drops():
    @render_converts_to(
        conversions={"renamed": "source", "derived": lambda self, clean: clean["a"] * 2}, drop=["secret"]
    )
    class Model(BaseModel):
        a: int
        source: str
        secret: str

    m = Model(a=21, source="s", secret="x")
    assert m.render_context() == {"a": 21, "source": "s", "renamed": "s", "derived": 42}
    # the clean canonical dump is untouched by the projection
    assert m.model_dump(mode="json") == {"a": 21, "source": "s", "secret": "x"}


def test_render_converts_to_is_the_identity_without_conversions():
    @render_converts_to()
    class Model(BaseModel):
        a: int
        b: str

    m = Model(a=1, b="x")
    assert m.render_context() == m.model_dump(mode="json")


def test_render_context_defaults_to_clean_dump():
    class Model(RenderedObject, BaseModel):
        a: int

    m = Model(a=5)
    assert m.render_context() == m.model_dump(mode="json")
    # the default projection is the identity, so get_rendering_context() (after
    # the schema check) yields the clean dump
    assert m.get_rendering_context() == m.model_dump(mode="json")
