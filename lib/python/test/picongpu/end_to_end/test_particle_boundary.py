"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+

End-to-end test for the per-species particle boundary conditions
(``Species.picongpu_particle_boundary``, issue #87 / PR #106).

A single small simulation exercises all four PIConGPU particle-boundary
kinds, one per species, so each kind's effect on the particles is observed
directly from the dumped particle data. Each species is a single thin slab of
macroparticles placed right at (or just inside) its active boundary and
drifting into it at 0.5 c, so it crosses that boundary within the first few
steps:

- **periodic** (species ``pbcPeriodic``): the x field is periodic, so the x
  particle boundary is periodic. Particles in the last x-column drift in +x;
  they cross the periodic x boundary and wrap around to the far edge while
  surviving -> the particle count is preserved.
- **absorbing** (species ``pbcAbsorbing``): the y field is open, so the y
  particle boundary is absorbing. Particles in the first y-row (the internal
  particle domain is the whole domain here, since the particle offset is 0)
  drift in -y; they cross the absorbing y boundary and are removed -> the
  particle count drops.
- **reflecting** (species ``pbcReflecting``): the z field is open, so the z
  particle boundary can be reflecting. Particles in the first z-column drift
  in -z; they cross the reflecting z boundary and bounce back into the domain
  while surviving -> the particle count is preserved.
- **thermal** (species ``pbcThermal``): the z field is open, so the z
  particle boundary can be thermal. Particles in the first internal z-column
  (just inside the positive offset) drift in -z; they cross the thermal z
  boundary and are re-momentum-sampled inward while surviving -> the particle
  count is preserved. (A thermal boundary requires a positive offset in the
  C++ core, so ``pbcThermal`` also carries ``boundary_offset`` /
  ``boundary_temperature``.)

Why all four fit in one simulation: the C++ per-axis constraint is
"field periodic => particle periodic; field open => absorbing/reflect/
thermal". The field boundary is per-axis, and there are only three axes. With
field BCs ``[periodic, open, open]`` the x-axis is forced to periodic and the
y/z-axes accept absorbing/reflect/thermal. Each species drifts only along its
active axis and is placed mid-domain on the other two axes, so exactly one
boundary kind acts per species. All four distinct kinds are covered, which is
the maximum possible (there are exactly four kinds).

The thermal species' non-active boundaries are set to non-removing kinds
(periodic on x, reflecting on y) rather than absorbing: the thermal boundary
re-samples the particle's full momentum on every crossing, so the particle
would otherwise drift at random and could be removed by an absorbing boundary,
making the "count preserved" assertion flaky. With only non-removing
boundaries the thermal particle can never be removed, so its count is
deterministically preserved.

Grid sizing (driven by C++ runtime constraints, not Python): the C++ core's
convolutional-PML field absorber (used for the "open" field boundaries,
``--fieldAbsorber pml`` by default) is 12 cells thick on each open side
(``fieldAbsorber.param`` ``NUM_CELLS``), and ``Pml::checkLocalThickness``
throws if the PML size exceeds the local domain. So the two open axes (y, z)
need at least 24 cells each; the periodic axis (x) needs no absorber and only
guard cells. The grid is therefore ``[32, 32, 32]`` with a ``[2, 2, 2]``
supercell: the open axes are wide enough for the PML to fit, and the whole
grid is still small. The step count is tiny (5), so the run is fast;
compilation (the heavy part) happens once for the single simulation object.
The ``free-streaming`` pusher ignores the EM fields, so the particles move in
straight lines and the boundary interactions are deterministic. The density is
chosen so that each slab cell holds exactly ``MACRO_PER_CELL`` macroparticles
with a per-particle weighting above ``MIN_WEIGHTING`` (see
``particle.param``), giving a small, non-zero, deterministic initial count.
"""

import logging
from pathlib import Path
from unittest import TestCase

import openpmd_api as opmd
import sympy
from picongpu import rc_params
from picongpu.picmi import (
    AnalyticDistribution,
    Cartesian3DGrid,
    ElectromagneticSolver,
    PseudoRandomLayout,
    Simulation,
    Species,
)
from picongpu.picmi.diagnostics import ParticleDump, TimeStepSpec
from picongpu.picmi.particle_boundary import ParticleBoundary

from .arbitrary_parameters import directory_in_home, gather_results

logging.basicConfig(level=logging.INFO)

C = 299792458.0
# x is periodic (no PML, needs only guard cells), y/z are open (PML 12 cells/
# side = 24 per axis, so they need >= 24 cells each). See the module docstring.
NUMBER_OF_CELLS = [32, 32, 32]
CELL_SIZE = 1.0
SUPER_CELL = (2, 2, 2)
# Minimal step budget: each particle is placed at (or within half a cell of)
# its active boundary and drifts at 0.5 c (about 0.29 cells per step), so it
# crosses its boundary within the first few steps; five steps leaves ample
# margin beyond that.
MAX_STEPS = 5
VELOCITY = 0.5 * C
# DENSITY * base_density * cell_volume == DENSITY macro-particles in the slab
# cell; the layout keeps at most MACRO_PER_CELL of them, each with a weighting
# of DENSITY / MACRO_PER_CELL. That weighting is >= MIN_WEIGHTING (10, see
# particle.param), so the slab cell deterministically holds exactly
# MACRO_PER_CELL particles.
DENSITY = 100.0
MACRO_PER_CELL = 8

LAYOUT = PseudoRandomLayout(n_macroparticles_per_cell=MACRO_PER_CELL)


def _slab(x, y, z, cx, cy, cz):
    # density DENSITY inside the single cell (cx, cy, cz), 0 everywhere else.
    # The density expression is evaluated at the SI cell-center position, so a
    # cell of size 1 occupies the interval [cx, cx + 1) on each axis.
    return sympy.Piecewise(
        (DENSITY, sympy.And(x >= cx, x < cx + 1, y >= cy, y < cy + 1, z >= cz, z < cz + 1)),
        (0.0, True),
    )


def _species(name, cell, velocity, boundary, offset=None, temperature=None):
    pb_kwargs = {"boundary": boundary}
    if offset is not None:
        pb_kwargs["boundary_offset"] = offset
    if temperature is not None:
        pb_kwargs["boundary_temperature"] = temperature
    return Species(
        name=name,
        particle_type="electron",
        method="free-streaming",
        initial_distribution=AnalyticDistribution(lambda x, y, z: _slab(x, y, z, *cell), directed_velocity=velocity),
        picongpu_particle_boundary=ParticleBoundary(**pb_kwargs),
    )


SPECIES = [
    # periodic: drift +x from the last x-column -> crosses the periodic x boundary
    # and wraps around to the far x-edge while surviving.
    _species("pbcPeriodic", (31, 16, 16), [VELOCITY, 0.0, 0.0], ["periodic", "absorbing", "absorbing"]),
    # absorbing: drift -y from the first y-row -> crosses the absorbing y boundary
    # and is removed.
    _species("pbcAbsorbing", (16, 0, 16), [0.0, -VELOCITY, 0.0], ["periodic", "absorbing", "absorbing"]),
    # reflecting: drift -z from the first z-column -> crosses the reflecting z
    # boundary and bounces back into the domain while surviving.
    _species("pbcReflecting", (16, 16, 0), [0.0, 0.0, -VELOCITY], ["periodic", "absorbing", "reflect"]),
    # thermal: drift -z from the first internal z-column (just inside the positive
    # offset) -> crosses the thermal z boundary and is re-momentum-sampled inward
    # while surviving. A thermal boundary requires a positive offset, so it also
    # carries an offset and a temperature. The non-active boundaries (x, y) are
    # non-removing kinds (periodic, reflecting) so the re-momentum-sampled
    # particle can never be removed, keeping the "count preserved" assertion
    # deterministic.
    _species(
        "pbcThermal",
        (16, 16, 1),
        [0.0, 0.0, -VELOCITY],
        ["periodic", "reflect", "thermal"],
        offset=[0, 0, 1],
        temperature=[0.0, 0.0, 10.0],
    ),
]


def basic_simulation():
    return Simulation(
        max_steps=MAX_STEPS,
        picongpu_base_density=1.0,
        solver=ElectromagneticSolver(
            method="Yee",
            cfl=1.0,
            grid=Cartesian3DGrid(
                number_of_cells=NUMBER_OF_CELLS,
                lower_bound=[0.0, 0.0, 0.0],
                upper_bound=[c * CELL_SIZE for c in NUMBER_OF_CELLS],
                lower_boundary_conditions=["periodic", "open", "open"],
                upper_boundary_conditions=["periodic", "open", "open"],
                picongpu_super_cell_size=SUPER_CELL,
            ),
        ),
    )


# Dump only the initial state (step 0) and the final state (step MAX_STEPS).
# All four species share the default openPMD file, so they are written into the
# same per-step files and can be read back per species.
def _diagnostics():
    period = TimeStepSpec[0] + TimeStepSpec[MAX_STEPS]
    return [ParticleDump(species=s, period=period) for s in SPECIES]


RUN_DIR = ""


def setup_sim():
    sim = basic_simulation()
    for species in SPECIES:
        sim.add_species(species, LAYOUT)
    sim.diagnostics = _diagnostics()
    if "rosi-hzdr" in rc_params.get("preset", "bash"):
        # On ROSI, the tmp directories are inaccessible to compute nodes.
        sim.picongpu_get_runner().setup_dir = directory_in_home() / "setup"
        sim.picongpu_get_runner().run_dir = directory_in_home() / "run"
    if RUN_DIR:
        sim.picongpu_get_runner().run_dir = RUN_DIR
    else:
        sim.step(MAX_STEPS)
    return sim


# only run this once, so we don't compile each and every time
SIM = None


class TestParticleBoundary(TestCase):
    _result_path = None

    def setUp(self):
        global SIM
        if SIM is None:
            SIM = setup_sim()
            self.sim = SIM
            gather_results(self.result_path)
        self.sim = SIM

    @property
    def result_path(self):
        if self._result_path is None:
            self._result_path = Path(self.sim.picongpu_get_runner().run_dir)
        return self._result_path

    def _count(self, step, name):
        # PIConGPU's openPMD output uses a file-based iteration layout where
        # each step is its own file and the iteration inside it is keyed by the
        # step number (not by position), so the final state is read via
        # ``iterations[MAX_STEPS]`` (the helper ``read_particles`` only reads
        # ``iterations[0]``, which is the initial state).
        path = self.result_path / "simOutput" / "openPMD" / f"simData_{step:06d}.bp5"
        series = opmd.Series(str(path), opmd.Access.read_only)
        try:
            particles = series.iterations[step].particles[name]
            count = int(len(particles["weighting"][""].load_chunk()))
        finally:
            series.flush()
        return count

    def test_periodic_preserves_particles(self):
        # particles crossing the periodic boundary wrap around and survive
        initial = self._count(0, "pbcPeriodic")
        final = self._count(MAX_STEPS, "pbcPeriodic")
        assert initial > 0, "no particles were created for the periodic species"
        assert final == initial, f"periodic boundary must preserve particles (initial={initial}, final={final})"

    def test_absorbing_removes_particles(self):
        # particles crossing the absorbing boundary are removed
        initial = self._count(0, "pbcAbsorbing")
        final = self._count(MAX_STEPS, "pbcAbsorbing")
        assert initial > 0, "no particles were created for the absorbing species"
        assert final < initial, f"absorbing boundary must remove particles (initial={initial}, final={final})"

    def test_reflecting_preserves_particles(self):
        # particles crossing the reflecting boundary bounce back and survive
        initial = self._count(0, "pbcReflecting")
        final = self._count(MAX_STEPS, "pbcReflecting")
        assert initial > 0, "no particles were created for the reflecting species"
        assert final == initial, f"reflecting boundary must preserve particles (initial={initial}, final={final})"

    def test_thermal_preserves_particles(self):
        # particles crossing the thermal boundary are re-momentum-sampled and survive
        initial = self._count(0, "pbcThermal")
        final = self._count(MAX_STEPS, "pbcThermal")
        assert initial > 0, "no particles were created for the thermal species"
        assert final == initial, f"thermal boundary must preserve particles (initial={initial}, final={final})"
