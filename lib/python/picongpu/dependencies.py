"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: PIConGPU contributors
License: GPLv3+
"""

# DRAFT: configuration surface for the installation of PIConGPU's compiled
# C++ dependencies (PNGwriter, FFTW3, openPMD-api, ...).
#
# This is the Python side of the provider abstraction; the actual work is
# done by the shell installer at etc/picongpu/dependencies/picongpu-deps.sh.
# See TASK-12-FINDINGS.md for the design discussion and trade-offs.
#
# picongpurc.toml (DRAFT section):
#
#     [dependencies]
#     enabled = true          # opt-in; default false (no behaviour change)
#     provider = "source"     # source | conda | modules | container
#     prefix = ""             # DEPS_INSTALL_ROOT (managed mode); default: <setup_dir>/deps
#     cache = ""              # DEPS_SOURCE_CACHE (shared source cache)
#     jobs = 16
#     only = []               # subset, e.g. ["fftw3", "pngwriter"]
#     force = false
#     offline = false
#     quiet = false
#     [dependencies.versions] # overrides, e.g. openpmd = "0.17.1"

from dataclasses import dataclass, field
from pathlib import Path

PROVIDERS = ("source", "conda", "modules", "container")

# dependency key -> version-override environment variable of picongpu-deps.sh
VERSION_VARS = {
    "boost": "DEPS_BOOST_VERSION",
    "c-blosc2": "DEPS_C_BLOSC2_VERSION",
    "libpng": "DEPS_LIBPNG_VERSION",
    "pngwriter": "DEPS_PNGWRITER_VERSION",
    "hdf5": "DEPS_HDF5_VERSION",
    "adios2": "DEPS_ADIOS2_VERSION",
    "openpmd": "DEPS_OPENPMD_VERSION",
    "fftw3": "DEPS_FFTW3_VERSION",
}

_KNOWN_KEYS = {
    "enabled",
    "provider",
    "prefix",
    "cache",
    "jobs",
    "only",
    "force",
    "offline",
    "quiet",
    "versions",
}


@dataclass(frozen=True)
class DependenciesConfig:
    enabled: bool = False
    provider: str = "source"
    prefix: str | None = None
    cache: str | None = None
    jobs: int | None = None
    only: tuple[str, ...] = ()
    force: bool = False
    offline: bool = False
    quiet: bool = False
    versions: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_rc_params(cls, rc_params) -> "DependenciesConfig":
        data = dict(rc_params.get("dependencies") or {})
        unknown = set(data) - _KNOWN_KEYS
        if unknown:
            raise ValueError(f"Unknown keys in [dependencies]: {sorted(unknown)}; valid: {sorted(_KNOWN_KEYS)}")
        provider = str(data.get("provider", "source"))
        if provider not in PROVIDERS:
            raise ValueError(f"Unknown dependencies provider {provider!r}; valid: {list(PROVIDERS)}")
        only = tuple(data.get("only") or ())
        for key in only:
            if key not in VERSION_VARS:
                raise ValueError(f"Unknown dependency {key!r} in dependencies.only; valid: {sorted(VERSION_VARS)}")
        versions = {str(k): str(v) for k, v in (data.get("versions") or {}).items()}
        for key in versions:
            if key not in VERSION_VARS:
                raise ValueError(f"Unknown dependency {key!r} in dependencies.versions; valid: {sorted(VERSION_VARS)}")
        return cls(
            enabled=bool(data.get("enabled", False)),
            provider=provider,
            prefix=data.get("prefix") or None,
            cache=data.get("cache") or None,
            jobs=int(data["jobs"]) if data.get("jobs") is not None else None,
            only=only,
            force=bool(data.get("force", False)),
            offline=bool(data.get("offline", False)),
            quiet=bool(data.get("quiet", False)),
            versions=versions,
        )

    @property
    def active(self) -> bool:
        return self.enabled and self.provider == "source"

    def install_commands(self, deps_script: Path, install_root: Path) -> list[str]:
        """Shell lines that install the dependencies (idempotent)."""
        lines = [
            f'export DEPS_PROVIDER="{self.provider}"',
            f'export DEPS_INSTALL_ROOT="{Path(self.prefix) if self.prefix else install_root}"',
        ]
        if self.cache:
            lines.append(f'export DEPS_SOURCE_CACHE="{self.cache}"')
        if self.jobs is not None:
            lines.append(f'export DEPS_JOBS="{self.jobs}"')
        if self.only:
            lines.append(f'export DEPS_ONLY="{",".join(self.only)}"')
        for key, value in self.versions.items():
            lines.append(f'export {VERSION_VARS[key]}="{value}"')
        if self.force:
            lines.append("export DEPS_FORCE=1")
        if self.offline:
            lines.append("export DEPS_OFFLINE=1")
        if self.quiet:
            lines.append("export DEPS_QUIET=1")
        lines.append(f'bash "{deps_script}"')
        lines.append(f'if [ -f "{Path(self.prefix) if self.prefix else install_root}/current.env" ]; then')
        lines.append(f'    . "{Path(self.prefix) if self.prefix else install_root}/current.env"')
        lines.append("fi")
        return lines

    def env_commands(self, install_root: Path) -> list[str]:
        """Shell lines that load the environment of an existing install."""
        root = Path(self.prefix) if self.prefix else install_root
        return [
            f'if [ -f "{root}/current.env" ]; then',
            f'    . "{root}/current.env"',
            "fi",
        ]
