"""
Tests for the per-example ``# ci: no-compile`` opt-out of the compiling suite.

This file is part of PIConGPU.
Copyright 2025 PIConGPU contributors
License: GPLv3+
"""

import importlib.util
from pathlib import Path

import pytest

_TARGET = Path(__file__).resolve().parents[2] / "compiling" / "test_compileexamples.py"


@pytest.fixture(scope="module")
def compileexamples():
    module_spec = importlib.util.spec_from_file_location("test_compileexamples", _TARGET)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


def test_parses_whole_line_no_compile_comment(tmp_path, compileexamples):
    declaring = tmp_path / "main.py"
    declaring.write_text("# ci: no-compile\nfrom picongpu import picmi\n")
    assert compileexamples.carries_no_compile_flag(declaring) is True

    declaring.write_text("# CI: NO-COMPILE\n")
    assert compileexamples.carries_no_compile_flag(declaring) is True

    declaring.write_text("   # ci: no-compile   \n")
    assert compileexamples.carries_no_compile_flag(declaring) is True


def test_rejects_non_matching_comments(tmp_path, compileexamples):
    other = tmp_path / "main.py"
    other.write_text("# ci: picongpu\n# ci: no-python-compile\n")
    assert compileexamples.carries_no_compile_flag(other) is False

    other.write_text("# this only mentions the flag: ci: no-compile\n")
    assert compileexamples.carries_no_compile_flag(other) is False

    other.write_text("assert '# ci: no-compile' in 'some template literal'\n")
    assert compileexamples.carries_no_compile_flag(other) is False


def test_missing_file_is_not_no_compile(tmp_path, compileexamples):
    assert compileexamples.carries_no_compile_flag(tmp_path / "does_not_exist.py") is False


def test_example_params_have_stable_ids(compileexamples):
    ids = [param.id for param in compileexamples._example_params()]
    assert len(ids) == len(set(ids))
    assert ids  # the tree currently contains example scripts


@pytest.mark.parametrize("declares_flag", [True, False])
def test_example_params_wire_markers(tmp_path, compileexamples, declares_flag):
    (tmp_path / "main.py").write_text("# ci: no-compile\n" if declares_flag else "# plain\n")
    compileexamples.EXAMPLES = [tmp_path / "main.py"]
    (param,) = compileexamples._example_params()
    marker_names = {marker.name for marker in param.marks}
    if declares_flag:
        assert marker_names == {"ci_no_compile", "skip"}
    else:
        assert marker_names == set()
