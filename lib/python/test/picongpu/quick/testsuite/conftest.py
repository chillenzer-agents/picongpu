"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: opencode
License: GPLv3+
"""

import sys
import warnings
from pathlib import Path

import pytest

# The standalone post-simulation validation framework (lib/python/test/testsuite)
# is not part of the installed picongpu package, make it importable.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))


@pytest.fixture(autouse=True)
def _restore_template_config():
    """
    The framework's checkDirection() writes the resolved directory back into
    the (global) template config module via exec(). Reset the module state
    between tests so that no test observes another test's directories.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from testsuite.Template import config

    snapshot = dict(vars(config))
    yield
    for key in list(vars(config)):
        if key in snapshot:
            setattr(config, key, snapshot[key])
        else:
            delattr(config, key)
