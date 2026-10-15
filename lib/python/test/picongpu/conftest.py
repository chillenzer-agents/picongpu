"""
Pytest configuration for PIConGPU test suite.

This file is part of PIConGPU.
Copyright 2025 PIConGPU contributors
License: GPLv3+
"""

import pytest


def pytest_collection_modifyitems(items):
    """
    Automatically apply markers based on test file location.

    - Tests in compiling/ get @pytest.mark.slow
    - Tests in end_to_end/ get @pytest.mark.slow
    - Tests in quick/ remain unmarked (fast)
    """
    for item in items:
        # split on "/" and check directory parts directly instead of a
        # substring match on the whole nodeid so that a test file living in a
        # directory such as "not_a_compiling_dir/" is never mis-marked.
        parts = item.nodeid.split("/")

        if "compiling" in parts:
            item.add_marker(pytest.mark.slow)
            item.add_marker(pytest.mark.compiling)

        if "end_to_end" in parts:
            item.add_marker(pytest.mark.slow)
            item.add_marker(pytest.mark.end_to_end)
