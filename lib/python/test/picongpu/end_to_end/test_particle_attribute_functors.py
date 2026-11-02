"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: chillenzer-agents
License: GPLv3+

Compile/end-to-end coverage for the extended particle-attribute registry.

The test exercises a representative scalar (``particleId``), bool
(``radiationMask``) and vector (``probeE``) attribute through a Binning
diagnostic and a derived field.  It needs a full PIConGPU build and is
therefore only run with the ``end_to_end``/``slow`` test selection.
"""

from pathlib import Path

from picongpu.picmi import (
    Cartesian3DGrid,
    ElectromagneticSolver,
    GriddedLayout,
    ParticleFunctor,
    Simulation,
    Species,
)
from picongpu.picmi.diagnostics import BinSpec, Binning, BinningAxis, DerivedFieldDump
from picongpu.picmi.particle_functor import FilteredSpecies, MacroParticle, ParticleFilter

from .arbitrary_parameters import NUMBER_OF_CELLS, UPPER_BOUNDARY
from .distributions import Gaussian

LAYOUT = GriddedLayout(n_macroparticles_per_cell=[1, 1, 1])
SPECIES = Species(
    name="extended_attributes",
    particle_type="electron",
    initial_distribution=Gaussian().distributions["predefined"],
    particle_shape="other:counter",
)


@ParticleFunctor
def particle_id(particle: MacroParticle):
    return particle.get("particleId")


@ParticleFunctor
def probe_e_x(particle: MacroParticle):
    return particle.get("probeE")[0]


@ParticleFunctor
def position_x(particle: MacroParticle):
    return particle.get("position", origin="cell")[0]


@ParticleFunctor
def total_cell_idx_x(particle: MacroParticle):
    return particle.get("totalCellIdx")[0]


@ParticleFunctor
def deposition(particle: MacroParticle):
    return 1.0


@ParticleFilter
def radiation_marked(particle: MacroParticle) -> bool:
    return particle.get("radiationMask")


def build_simulation():
    simulation = Simulation(
        max_steps=0,
        solver=ElectromagneticSolver(
            method="Yee",
            cfl=1.0,
            grid=Cartesian3DGrid(
                number_of_cells=NUMBER_OF_CELLS,
                lower_bound=[0, 0, 0],
                upper_bound=UPPER_BOUNDARY,
                lower_boundary_conditions=["open", "open", "open"],
                upper_boundary_conditions=["open", "open", "open"],
            ),
        ),
    )
    simulation.add_species(SPECIES, LAYOUT)
    filtered = FilteredSpecies(species=SPECIES, functor=radiation_marked)
    simulation.diagnostics = [
        Binning(
            name="particleIdHistogram",
            deposition_functor=deposition,
            axes=[
                BinningAxis(
                    functor=particle_id,
                    bin_spec=BinSpec(kind="linear", start=0, stop=1000, nsteps=10),
                )
            ],
            species=filtered,
        ),
        DerivedFieldDump(species=filtered, functor=probe_e_x),
        DerivedFieldDump(species=SPECIES, functor=position_x),
        DerivedFieldDump(species=SPECIES, functor=total_cell_idx_x),
        DerivedFieldDump(species=SPECIES, functor=particle_id),
    ]
    return simulation


def test_extended_attributes_compile_and_run():
    simulation = build_simulation()
    # Rendering itself must already succeed and carry the registry types/units.
    rendered = particle_id.get_as_pypicongpu(mode="Binning")
    assert rendered.return_type == "uint64_t"
    assert probe_e_x.get_as_pypicongpu(mode="DerivedField").get_unit_cpp == "sim.unit.eField()"
    assert position_x.get_as_pypicongpu(mode="DerivedField").get_unit_cpp == "1."
    total_cell_idx = total_cell_idx_x.get_as_pypicongpu(mode="DerivedField")
    assert total_cell_idx.functor_preamble[0].statement == "auto const totalCellIdx_value = particle[totalCellIdx_];"

    simulation.step(0)
    run_dir = Path(simulation.picongpu_get_runner().run_dir)
    assert run_dir.exists()
    # The species must carry all three accessed attributes.
    species_definition = (run_dir / "input" / "include" / "picongpu" / "param" / "speciesDefinition.param").read_text()
    for attribute in ("particleId", "radiationMask", "probeE", "totalCellIdx"):
        assert attribute in species_definition
