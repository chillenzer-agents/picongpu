"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+

End-to-end test of the radiation plugin's name-based particle filter.

NOTE: this test exercises the *stacked* C++ + Python flow and therefore
requires the Python-side `FilteredSpecies` support for the radiation
diagnostic (see the radiation PICMI filters work). That prerequisite is not
part of this C++ change, so the test skips cleanly in this PR's own CI and is
intended to run in the CI of the stacked PRs (it is a compile/C++ gate item
for the `.filter` kernel path).
"""

import logging
import re
from functools import partial
from pathlib import Path
from unittest import TestCase

import numpy as np
import openpmd_api as opmd
from picongpu import rc_params
from picongpu.picmi import (
    Cartesian3DGrid,
    ElectromagneticSolver,
    FilteredSpecies,
    ParticleFilter,
    PseudoRandomLayout,
    Simulation,
    Species,
    UniformDistribution,
)
from picongpu.picmi.diagnostics import Radiation, TimeStepSpec
from picongpu.pypicongpu.output.radiation import RadiationObserverConfiguration
from sympy import And

from .arbitrary_parameters import directory_in_home, gather_results

logging.basicConfig(level=logging.INFO)

#: cells per direction of the (cubic) simulation box
N_CELLS = 16
#: number of macro particles per cell per species
PARTICLES_PER_CELL = 8
#: total number of simulation steps
N_STEPS = 100

#: the filter keeps only the center of the box in x-direction (in cells);
#: the particles in the excluded slices still exist and may radiate
FILTER_LOW, FILTER_HIGH = 4, 12

#: the filter keeps exactly the middle half of the simulation box in x, so the
#: radiation of the filtered species must drop well below the unfiltered
#: reference. The two species are independent random draws, so a plain strict
#: ``<`` is too fragile (the filtered species could occasionally radiate
#: marginally more than the unfiltered one); a generous relative drop proves
#: the filter is active without depending on exact macro-particle equality.
RELATIVE_DROP = 0.10

#: open_name of the radiation output record holding the complex amplitude
_AMPLITUDE_RECORD = "Amplitude"
_AMPLITUDE_COMPONENTS = ["x_Re", "x_Im", "y_Re", "y_Im", "z_Re", "z_Im"]


def make_observer():
    """observer with a small number of directions to keep the output manageable"""
    return RadiationObserverConfiguration(N_observer=16, index_to_direction=lambda _: [1, 0, 0])


def range_filter(particle, lo, hi):
    """keep only the particles in the center of the box in x-direction"""
    position = particle.get("position", origin="total", unit="cell")
    return And(position[0] >= lo, position[0] < hi)


def make_radiation_diagnostic(species):
    return Radiation(species=species, period=TimeStepSpec[2::2], observer=make_observer())


def basic_simulation():
    """a small, self-consistent electron plasma that accelerates on its own"""
    physical_box = 1.0  # meter
    cell_m = physical_box / N_CELLS
    grid = Cartesian3DGrid(
        number_of_cells=[N_CELLS, N_CELLS, N_CELLS],
        lower_bound=[0, 0, 0],
        upper_bound=[physical_box, physical_box, physical_box],
        lower_boundary_conditions=["open", "open", "open"],
        upper_boundary_conditions=["open", "open", "open"],
    )
    solver = ElectromagneticSolver(method="Yee", grid=grid, cfl=1.0)
    # CFL-consistent time step for the Yee scheme with cfl = 1
    speed_of_light = 299792458.0
    dt = cell_m / (np.sqrt(3.0) * speed_of_light)
    return Simulation(time_step_size=dt, max_steps=N_STEPS, solver=solver)


def _make_species(name):
    species = Species(name=name, particle_type="electron", initial_distribution=UniformDistribution(density=1.0e25))
    return species


def setup_sim():
    """build and run one simulation with an unfiltered reference species and a filtered species

    Both species are set up identically; the filtered one additionally keeps only
    the center of the box in x-direction via a particle filter.
    """
    sim = basic_simulation()

    species_reference = _make_species("electron")
    sim.add_species(species_reference, PseudoRandomLayout(n_macroparticles_per_cell=PARTICLES_PER_CELL))
    sim.diagnostics = [make_radiation_diagnostic(species_reference)]

    species_filtered = _make_species("electronFiltered")
    sim.add_species(species_filtered, PseudoRandomLayout(n_macroparticles_per_cell=PARTICLES_PER_CELL))
    filtered = FilteredSpecies(
        species=species_filtered,
        functor=ParticleFilter(name="rangeFilter", functor=partial(range_filter, lo=FILTER_LOW, hi=FILTER_HIGH)),
    )
    sim.diagnostics.append(make_radiation_diagnostic(filtered))

    if "rosi-hzdr" in rc_params.get("preset", "bash"):
        # On ROSI, the tmp directories are inaccessible to compute nodes.
        sim.picongpu_get_runner().setup_dir = directory_in_home() / "setup"
        sim.picongpu_get_runner().run_dir = directory_in_home() / "run"
    sim.step(N_STEPS)
    return Path(sim.picongpu_get_runner().run_dir)


def _find_latest_radiation_file(result_path, species_name):
    """find the radiation output file of the last dumped time step for a species"""
    pattern = re.compile(rf"{re.escape(species_name)}_radAmplitudes_(\d+)_0_0_0\.h5")
    matches = [(int(m.group(1)), path) for path in result_path.rglob("*.h5") if (m := pattern.search(path.name))]
    assert matches, f"no radiation output found for species {species_name} under {result_path}"
    return max(matches, key=lambda entry: entry[0])[1]


def _radiation_intensity(result_path, species_name):
    """total emitted radiation intensity of a species summed over observers/frequencies

    The radiation plugin writes the complex per-observer/per-frequency amplitude
    into the ``Amplitude`` record of its openPMD output. The (real, non-negative)
    radiation intensity is the squared magnitude of this amplitude; summing it
    over all observers, frequencies and components yields the total emitted
    energy, which is additive over the emitting particles.
    """
    path = _find_latest_radiation_file(result_path, species_name)
    with opmd.Series(str(path), opmd.Access.read_only) as series:
        # exactly one iteration is expected in the final file
        iteration = max(series.iterations)
        amplitude = series.iterations[iteration].meshes[_AMPLITUDE_RECORD]
        squared_magnitudes = [np.square(amplitude[component].load_chunk()) for component in _AMPLITUDE_COMPONENTS]
    return float(np.sum(squared_magnitudes))


class RadiationFilteredSpecies:
    """probe for the picmi.Radiation FilteredSpecies support (a Python-side prerequisite)"""

    def _supported():
        try:
            species = _make_species("probe")
            filtered = FilteredSpecies(
                species=species,
                functor=ParticleFilter(name="rangeFilter", functor=partial(range_filter, lo=0, hi=N_CELLS)),
            )
            make_radiation_diagnostic(filtered)
        except Exception:
            return False
        return True


class TestRadiation(TestCase):
    """first end-to-end (compiled PIConGPU) test of the radiation plugin

    Compares the total emitted radiation intensity of an unfiltered species
    against an identically set-up species whose particle filter keeps only the
    center of the box.
    """

    _results = None

    def setUp(self):
        if TestRadiation._results is None:
            # The python-side FilteredSpecies support for Radiation is a
            # prerequisite (radiation PICMI filters) that is not part of this
            # C++ change; skip cleanly if it is not available in this
            # environment. The test runs in the CI of the stacked PRs.
            if not RadiationFilteredSpecies._supported():
                self.skipTest(
                    "environment does not provide FilteredSpecies support for Radiation; "
                    "test runs in the stacked (radiation PICMI filters + this change) CI"
                )
            result_path = setup_sim()
            gather_results(result_path)
            TestRadiation._results = {
                "reference": _radiation_intensity(result_path, "electron"),
                "filtered": _radiation_intensity(result_path, "electronFiltered"),
            }

    def test_filtered_radiation_is_subset_of_reference(self):
        reference = self._results["reference"]
        filtered = self._results["filtered"]

        # the plasma must actually produce radiation, otherwise the comparison is meaningless
        assert reference > 0.0, "unfiltered radiation is zero -- no particles accelerated?"
        # a subset of emitters may never radiate more energy than the full set
        assert filtered <= reference * (1.0 + 1e-6), f"filtered {filtered} exceeds reference {reference}"
        # the filter removes a substantial part of the emitters, so the total must drop clearly; a strict
        # ``filtered < reference`` would be fragile because the two species are independently seeded random
        # draws and not exact macro-particle subsets of each other, so require a non-degenerate relative drop.
        assert filtered < reference * (1.0 - RELATIVE_DROP), (
            f"filtered {filtered} not below reference {reference} by a relative {RELATIVE_DROP} margin"
        )
