"""
This file is part of PIConGPU.
Copyright 2021-2025 PIConGPU contributors
Authors: Brian Edward Marre, Julian Lenz
License: GPLv3+
"""

import re
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest
from picongpu import pypicongpu

EXAMPLES = list((Path(__file__).parents[3] / "examples").glob("*/main.py"))

# Per-example opt-out mirroring the job-level `ci: no-compile` flag: an example
# script declaring a whole-line `# ci: no-compile` comment is skipped by the
# compiling suite (and deselectable via `-m "not ci_no_compile"`), while still
# being generatable/compilable locally by hand.
_NO_COMPILE_COMMENT = re.compile(r"^\s*#\s*ci:\s*no-compile\s*$", re.IGNORECASE)


def carries_no_compile_flag(example: Path) -> bool:
    """Return True if the example script declares the ``# ci: no-compile`` opt-out."""
    if not example.is_file():
        return False
    return any(_NO_COMPILE_COMMENT.match(line) for line in example.read_text().splitlines())


def _example_params():
    for example in sorted(EXAMPLES):
        if carries_no_compile_flag(example):
            yield pytest.param(
                example,
                id=example.parent.name,
                marks=[
                    pytest.mark.ci_no_compile,
                    pytest.mark.skip(reason="example declares the `# ci: no-compile` opt-out"),
                ],
            )
        else:
            yield pytest.param(example, id=example.parent.name)


@pytest.fixture(params=list(_example_params()))
def sim(request):
    """The simulation object defined in the corresponding example script."""
    module_spec = spec_from_file_location("example", request.param)
    module = module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module.sim


def test_compile_example(sim):
    """Attempts to compile the given simulation."""
    runner = pypicongpu.Runner(sim=sim)
    runner.generate(printDirToConsole=True)
    runner.build()
