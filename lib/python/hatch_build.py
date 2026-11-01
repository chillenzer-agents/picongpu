"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+

Hatch build hook that ships the PIConGPU core trees with the Python package.

In a source checkout the trees live at the repository root, outside of
``lib/python``. They are copied into the package as ``picongpu/core/<tree>``
so that ``picongpu.core.path()`` finds them after installation. When building
from an extracted sdist those trees are already inside the package, and the
checkout-relative sources do not exist; in that case no mapping is added and
the regular package inclusion takes care of them.
"""

from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

# source path relative to the project root -> destination path in the artifact
CORE_TREES = {
    "../../include": "picongpu/core/include",
    "../../etc": "picongpu/core/etc",
    "../../bin": "picongpu/core/bin",
    "../../src/tools/bin": "picongpu/core/bin",
    "../../share/picongpu/examples": "picongpu/core/share/picongpu/examples",
    "../../thirdParty": "picongpu/core/thirdParty",
}


class CoreTreesBuildHook(BuildHookInterface):
    """Copy the checkout's core trees into the sdist/wheel package."""

    def initialize(self, version, build_data):
        root = Path(self.root)
        # The project root is <repo>/lib/python in a source checkout. Only add
        # the checkout-relative mappings then; a build from an extracted sdist
        # has the trees inside the package already.
        checkout_root = root / "../.."
        if not (checkout_root / "lib" / "python" / "pyproject.toml").exists():
            return
        missing = sorted(source for source in CORE_TREES if not (root / source).exists())
        if missing:
            raise FileNotFoundError(
                "PIConGPU core tree(s) missing from the source checkout: "
                + ", ".join(missing)
                + ". Build from a complete checkout, or from an extracted sdist "
                "which already contains them in the package."
            )
        build_data["force_include"].update(CORE_TREES)
