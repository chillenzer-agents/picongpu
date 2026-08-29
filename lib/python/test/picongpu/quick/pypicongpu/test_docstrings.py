"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+

Docstring completeness check (task 06): every pydantic BaseModel subclass in
picongpu.pypicongpu must have a class docstring, and every public annotated
field a docstring (the string literal directly following the annotation,
which is the pydantic house idiom). The checks are AST-based so they hold
independently of pydantic's introspection.
"""

import ast
import importlib
import pkgutil

import pydantic
import pytest

import picongpu.pypicongpu as pypicongpu


def _find_models():
    """Return a list of (module_name, class) for all BaseModel subclasses in pypicongpu."""
    seen = set()
    models = []
    for module_info in pkgutil.walk_packages(pypicongpu.__path__, prefix="picongpu.pypicongpu."):
        try:
            module = importlib.import_module(module_info.name)
        except Exception:
            continue
        for name in dir(module):
            obj = getattr(module, name)
            if (
                isinstance(obj, type)
                and issubclass(obj, pydantic.BaseModel)
                and obj.__module__ == module_info.name
                and obj.__name__ not in seen
            ):
                seen.add(obj.__name__)
                models.append((module_info.name, obj))
    return models


def _class_node(tree, qualname):
    """Find the ClassDef node for the given qualname in the parsed module tree."""

    def walk(nodes, prefix):
        for node in nodes:
            if isinstance(node, ast.ClassDef):
                qname = ".".join(prefix + [node.name])
                if qname == qualname:
                    return node
                found = walk(node.body, prefix + [node.name])
                if found is not None:
                    return found
        return None

    return walk(tree.body, [])


def _docstring(stmts, index):
    """Return the string literal at stmts[index], if it is a plain string expression."""
    stmt = stmts[index]
    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str):
        return stmt.value.value
    return None


def _check_model(module_name, cls):
    """Return a list of violation strings for one model class."""
    path = importlib.import_module(module_name).__file__
    with open(path) as file:
        tree = ast.parse(file.read(), filename=path)
    node = _class_node(tree, cls.__qualname__)
    if node is None:
        return [f"{cls.__qualname__}: could not find class node in {path}"]

    violations = []
    if _docstring(node.body, 0) is None:
        violations.append(f"{cls.__qualname__}: missing class docstring")

    for i, stmt in enumerate(node.body):
        if not isinstance(stmt, ast.AnnAssign):
            continue
        if not (isinstance(stmt.target, ast.Name) and stmt.target.id and not stmt.target.id.startswith("_")):
            continue
        if _docstring(node.body, i + 1) is None:
            violations.append(f"{cls.__qualname__}.{stmt.target.id}: missing field docstring (line {stmt.lineno})")
    return violations


_MODELS = _find_models()


@pytest.mark.parametrize(("module_name", "cls"), _MODELS, ids=lambda c: c.__qualname__ if isinstance(c, type) else c)
def test_model_docstrings(module_name, cls):
    assert _check_model(module_name, cls) == []
