#!/usr/bin/env python
# /// script
# requires-python = ">=3.11,<3.14"
# dependencies = [
#   "picongpu @ git+https://github.com/ComputationalRadiationPhysics/picongpu@dev#subdirectory=lib/python"
# ]
# ///
"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+

Shows that `translate()` resolves constraints from the objects reachable from
the simulation: an ionization model that is constructed but never added to
`picongpu_interaction` contributes nothing, while an added model does.
"""

# BEGIN-TRANSLATE-REACHABILITY
from picongpu import picmi
from picongpu.picmi.translate import translate


def build(added):
    """Build a simulation with an ADK model either added or left unused."""
    grid = picmi.Cartesian3DGrid(
        number_of_cells=[32, 32, 32],
        lower_bound=[0, 0, 0],
        upper_bound=[1e-6, 1e-6, 1e-6],
        lower_boundary_conditions=["periodic", "periodic", "periodic"],
        upper_boundary_conditions=["periodic", "periodic", "periodic"],
    )
    solver = picmi.ElectromagneticSolver(method="Yee", cfl=0.5, grid=grid)
    hydrogen = picmi.Species(
        name="hydrogen",
        particle_type="H",
        charge_state=0,
        initial_distribution=picmi.UniformDistribution(density=1e23),
    )
    electrons = picmi.Species(
        name="electrons",
        particle_type="electron",
        initial_distribution=None,
    )
    adk = picmi.ADK(
        ADK_variant=picmi.ADKVariant.LinearPolarization,
        ion_species=hydrogen,
        ionization_electron_species=electrons,
        ionization_current=None,
    )
    return picmi.Simulation(
        max_steps=10,
        solver=solver,
        species=[hydrogen, electrons],
        layouts=[picmi.PseudoRandomLayout(n_macroparticles_per_cell=1), None],
        picongpu_interaction=[adk] if added else [],
    )


def has_ionization(sim):
    """Whether translating `sim` derives ground-state ionization for hydrogen."""
    resolved = translate(sim)
    hydrogen = next(species for species in resolved.species if species.name == "hydrogen")
    return hydrogen.constants.ground_state_ionization is not None


print("unused model -> ionization:", has_ionization(build(added=False)))
print("added model  -> ionization:", has_ionization(build(added=True)))
# END-TRANSLATE-REACHABILITY
