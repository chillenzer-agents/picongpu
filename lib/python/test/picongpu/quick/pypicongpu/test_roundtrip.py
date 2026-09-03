"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+

Round-trip safety (task 07): a model's serialised output
(``model_dump(mode="json")``) must be accepted again by the model, and
re-serialising the reconstructed instance must yield the identical dump.

This is checked with ``model_validate`` -- the canonical "reconstruct a valid
instance from on-disk serialised JSON" path -- so that the (machine-readable)
constraints and validators captured in the pydantic models do not reject the
models' own serialisation, and so that a full ``Runner``/``Simulation`` can be
rebuilt from the metadata JSONs written during ``generate()``.

The corpus covers every model whose serialisation is field-preserving, as well
as the models that needed (de)serialisation fixes to become lossless
(solvers, lasers, openPMD plugin, binning, elements, ionization models,
collisions, radiation observer, operations, ...). Models whose top-level
``model_serializer`` produces a rendering-oriented form (e.g. the openPMD
plugin) are covered both here (their ``model_dump`` now carries the full state)
and by the rendered-output regression.
"""

from datetime import timedelta
from pathlib import Path
import json
import tempfile

import pytest
from sympy import Symbol

from picongpu import picmi
from picongpu.picmi.interaction import Collision as PicmiCollision
from picongpu.picmi.interaction import CollisionalPhysicsSetup as PicmiCollisionalPhysicsSetup
from picongpu.pypicongpu.runner import Runner
from picongpu.pypicongpu.simulation import Simulation
from picongpu.pypicongpu.collisions import (
    Collision,
    CollisionNumericsConfig,
    CollisionalPhysicsSetup,
    ConstLogCollision,
    DynamicLogCollision,
)
from picongpu.pypicongpu.customuserinput import CustomUserInput
from picongpu.pypicongpu.field_solver import LeheSolver, YeeSolver
from picongpu.pypicongpu.grid import BoundaryCondition, Grid3D
from picongpu.pypicongpu.laser import (
    DispersivePulseLaser,
    FromOpenPMDPulseLaser,
    GaussianLaser,
    PlaneWaveLaser,
    TWTSLaser,
)
from picongpu.pypicongpu.movingwindow import MovingWindow
from picongpu.pypicongpu.output.binning import Binning, BinningAxis, BinSpec
from picongpu.pypicongpu.output.checkpoint import Checkpoint
from picongpu.pypicongpu.output.energy_histogram import EnergyHistogram
from picongpu.pypicongpu.output.openpmd_plugin import FieldDump, OpenPMDConfig, OpenPMDPlugin, RangeSpec
from picongpu.pypicongpu.output.phase_space import PhaseSpace
from picongpu.pypicongpu.output.radiation import (
    LinearFrequencies,
    LogFrequencies,
    RadiationConfiguration,
    RadiationObserverConfiguration,
    RadiationPlugin,
    RadiationPluginConfig,
)
from picongpu.pypicongpu.output.timestepspec import Spec, TimeStepSpec
from picongpu.pypicongpu.particle_functor.filtered_species import FilteredSpecies
from picongpu.pypicongpu.particle_functor.particle_functor import ParticleFunctor
from picongpu.pypicongpu.particle_functor.rng_info import NormalRNGInfo
from picongpu.pypicongpu.species.attribute import BoundElectrons, Momentum, Position, Weighting
from picongpu.pypicongpu.species.constant import Charge, DensityRatio, ElementProperties, GroundStateIonization, Mass
from picongpu.pypicongpu.species.constant.ionizationcurrent import None_ as NoCurrent
from picongpu.pypicongpu.species.constant.ionizationmodel import (
    ADKCircularPolarization,
    ADKLinearPolarization,
    BSI,
    BSIEffectiveZ,
    BSIStarkShifted,
    Keldysh,
    ThomasFermi,
)
from picongpu.pypicongpu.species.constant.synchrotron import SynchrotronConstant, SynchrotronParams
from picongpu.pypicongpu.species.operation import SetChargeState, SimpleDensity, SimpleMomentum
from picongpu.pypicongpu.species.operation.densityprofile import Cylinder, Foil, FreeFormula, Uniform
from picongpu.pypicongpu.species.operation.densityprofile.gaussian import Gaussian
from picongpu.pypicongpu.species.operation.densityprofile.plasmaramp import Exponential
from picongpu.pypicongpu.species.operation.layout import OnePosition, Quiet, Random
from picongpu.pypicongpu.species.operation.momentum import Drift, Temperature
from picongpu.pypicongpu.species.species import Species
from picongpu.pypicongpu.species.util.element import Element
from picongpu.pypicongpu.walltime import Walltime

# shared building blocks -----------------------------------------------------

_LASER_KWARGS = dict(
    propagation_direction=(0.0, 1.0, 0.0),
    polarization_direction=(0.0, 0.0, 1.0),
    polarization_type="Linear",
    wave_length_si=0.8e-6,
    pulse_duration_si=1e-15,
    focus_pos_si=(0.5e-5, 0.5e-5, 0.5e-5),
    phase=0.0,
    E0_si=1e10,
    pulse_init=1.0,
    huygens_surface_positions=[[1, -1], [1, -1], [1, -1]],
)

_ELECTRON = Species(
    name="electron",
    constants=[Mass(mass_si=9.109e-31), Charge(charge_si=-1.602e-19)],
    attributes=[Position(), Weighting(), Momentum()],
)

_ION = Species(
    name="hydrogen",
    constants=[
        Mass(mass_si=1.67e-27),
        Charge(charge_si=1.602e-19),
        ElementProperties(element=Element(openpmd_name="H")),
        GroundStateIonization(
            ionization_model_list=[BSI(ionization_current=NoCurrent(), ionization_electron_species=_ELECTRON)]
        ),
    ],
    attributes=[Position(), Weighting(), Momentum(), BoundElectrons()],
)

_TSS = TimeStepSpec([Spec(start=0, stop=-1, step=10)])

_FUNCTOR = ParticleFunctor(
    name="gammaFilter",
    functor_expression=Symbol("px") ** 2 + Symbol("py") ** 2,
    functor_preamble=[],
    return_type="float_X",
)


def _build(name: str):
    if name == "Grid3D":
        return Grid3D(
            cell_size_si=(1e-6, 1e-6, 1e-6),
            cell_cnt=(16, 16, 16),
            boundary_condition=(BoundaryCondition.PERIODIC,) * 3,
            n_gpus=(1, 1, 1),
            super_cell_size=(2, 2, 2),
        )
    if name == "Walltime":
        return Walltime(walltime=timedelta(hours=1, minutes=2, seconds=3))
    if name == "MovingWindow":
        return MovingWindow(move_point=0.5, stop_iteration=100)
    if name == "YeeSolver":
        return YeeSolver()
    if name == "LeheSolver":
        return LeheSolver()
    if name == "GaussianLaser":
        return GaussianLaser(waist_si=1e-5, laguerre_modes=[1.0], laguerre_phases=[0.0], **_LASER_KWARGS)
    if name == "PlaneWaveLaser":
        return PlaneWaveLaser(laser_nofocus_constant_si=1.0, **_LASER_KWARGS)
    if name == "DispersivePulseLaser":
        return DispersivePulseLaser(
            waist_si=1e-5, spectral_support=1.0, sd_si=1e-29, ad_si=1e-28, gdd_si=1e-27, tod_si=1e-26, **_LASER_KWARGS
        )
    if name == "TWTSLaser":
        return TWTSLaser(
            waist_si=1e-5,
            laserIncidenceAngle=0.1,
            laserIncidenceAnglePositive=True,
            polarizationAngle=0.2,
            beta0=1.0,
            time_offset_si=0.0,
            focus_lateral_offset_si=0.0,
            windowStart=0.0,
            windowEnd=0.0,
            windowLength=0.0,
            **_LASER_KWARGS,
        )
    if name == "FromOpenPMDPulseLaser":
        return FromOpenPMDPulseLaser(
            propagation_direction=(0.0, 1.0, 0.0),
            polarization_direction=(0.0, 0.0, 1.0),
            file_path="pulse.h5",
            iteration=0,
            dataset_name="E",
            datatype="E_Cell",
            time_offset_si=0.0,
            polarisationAxisOpenPMD="x",
            propagationAxisOpenPMD="y",
            huygens_surface_positions=[[1, -1], [1, -1], [1, -1]],
        )
    if name == "Spec_full":
        return Spec(start=0, stop=-1, step=10)
    if name == "Spec_opt":
        return Spec(start=None, stop=None, step=None)
    if name == "TimeStepSpec":
        return _TSS
    if name == "Checkpoint":
        return Checkpoint(period=_TSS)
    if name == "Checkpoint_timePeriod":
        return Checkpoint(timePeriod=5)
    if name == "LinearFrequencies":
        return LinearFrequencies()
    if name == "LogFrequencies":
        return LogFrequencies(omega_min=1e14, omega_max=1e17)
    if name == "RadiationObserverConfiguration":
        return RadiationObserverConfiguration(index_to_direction=lambda _: [1, 0, 0], N_observer=1)
    if name == "RadiationObserverConfiguration_nonunit":
        # a non-unit direction exercises the validator's normalising branch
        return RadiationObserverConfiguration(index_to_direction=lambda i: (i, 1, 0), N_observer=1)
    if name == "RadiationConfiguration":
        return RadiationConfiguration(frequencies=LogFrequencies(omega_min=1e14, omega_max=1e17))
    if name == "RadiationPluginConfig":
        return RadiationPluginConfig(
            observer=RadiationObserverConfiguration(index_to_direction=lambda _: [1, 0, 0], N_observer=1)
        )
    if name == "RadiationPlugin":
        return RadiationPlugin(
            config=RadiationPluginConfig(
                observer=RadiationObserverConfiguration(index_to_direction=lambda _: [1, 0, 0], N_observer=1)
            ),
            species=[_ELECTRON],
            period=TimeStepSpec([Spec(start=10, stop=-1, step=100)]),
        )
    if name == "PhaseSpace":
        return PhaseSpace(
            species=_ELECTRON,
            period=_TSS,
            spatial_coordinate="x",
            momentum_coordinate="px",
            min_momentum=-1.0,
            max_momentum=1.0,
        )
    if name == "EnergyHistogram":
        return EnergyHistogram(
            species=_ELECTRON,
            period=_TSS,
            bin_count=16,
            min_energy=0.0,
            max_energy=100.0,
        )
    if name == "FieldDump_native":
        return FieldDump(name="gamma", functor=None, filtername=None)
    if name == "ParticleFunctor":
        return _FUNCTOR
    if name == "FieldDump_derived":
        return FieldDump(name="derivedField", functor=_FUNCTOR)
    if name == "FilteredSpecies":
        return FilteredSpecies(species=_ELECTRON, functor=_FUNCTOR)
    if name == "ParticleFunctor_rng":
        return ParticleFunctor(
            name="randomFunctor",
            functor_expression=Symbol("px") * 2,
            functor_preamble=[],
            return_type="float_X",
            rng_info=NormalRNGInfo(return_type="float_X"),
        )
    if name == "OpenPMDConfig":
        return OpenPMDConfig(file="simData", range=[None, 42, (1, 10)])
    if name == "RangeSpec":
        return RangeSpec()
    if name == "OpenPMDPlugin":
        return OpenPMDPlugin(
            sources=[
                (_TSS, _ELECTRON),
                (_TSS, FieldDump(name="derivedField", functor=_FUNCTOR)),
                (_TSS, FilteredSpecies(species=_ELECTRON, functor=_FUNCTOR)),
            ],
            config=OpenPMDConfig(file="simData"),
        )
    if name == "BinSpec":
        return BinSpec(kind="Linear", start=0, stop=10, nsteps=10)
    if name == "BinningAxis":
        return BinningAxis(
            name="x",
            bin_spec_raw=BinSpec(kind="Linear", start=0, stop=10, nsteps=10),
            functor=_FUNCTOR,
            use_overflow_bins=True,
        )
    if name == "Binning":
        return Binning(
            name="binner",
            deposition_functor=_FUNCTOR,
            axes=[
                BinningAxis(
                    name="x",
                    bin_spec_raw=BinSpec(kind="Linear", start=0, stop=10, nsteps=10),
                    functor=_FUNCTOR,
                    use_overflow_bins=True,
                )
            ],
            species=[_ELECTRON, FilteredSpecies(species=_ELECTRON, functor=_FUNCTOR)],
            period=_TSS,
            openPMDBackendConfig={"some": "config"},
            openPMDExt="h5",
            openPMDInfix="_%06T",
            dumpPeriod=10,
        )
    if name == "ConstLogCollision":
        return ConstLogCollision(coulomb_log=12.0)
    if name == "DynamicLogCollision":
        return DynamicLogCollision()
    if name == "Collision":
        return Collision(species_pairs=[(_ELECTRON, _ION)], functor=ConstLogCollision(coulomb_log=12.0))
    if name == "Collision_filters":
        return Collision(
            species_pairs=[(FilteredSpecies(species=_ELECTRON, functor=_FUNCTOR), _ION)], functor=DynamicLogCollision()
        )
    if name == "CollisionNumericsConfig":
        return CollisionNumericsConfig(precision=64, cell_list_chunk_size=128)
    if name == "CollisionalPhysicsSetup":
        return CollisionalPhysicsSetup(
            collisions=[
                Collision(
                    species_pairs=[(_ELECTRON, _ION), (_ELECTRON, _ELECTRON)],
                    functor=ConstLogCollision(coulomb_log=12.0),
                )
            ],
            screening_species=[_ELECTRON, _ION, FilteredSpecies(species=_ELECTRON, functor=_FUNCTOR)],
            numerics_config=CollisionNumericsConfig(),
        )
    if name == "Species":
        return _ELECTRON
    if name == "Species_ion":
        return _ION
    if name == "Position":
        return Position()
    if name == "Weighting":
        return Weighting()
    if name == "Momentum":
        return Momentum()
    if name == "BoundElectrons":
        return BoundElectrons()
    if name == "Mass":
        return Mass(mass_si=9.109e-31)
    if name == "Charge":
        return Charge(charge_si=-1.602e-19)
    if name == "DensityRatio":
        return DensityRatio(ratio=2.0)
    if name == "Element":
        return Element(openpmd_name="H")
    if name == "Element_isotope":
        return Element(openpmd_name="#14N")
    if name == "ElementProperties":
        return ElementProperties(element=Element(openpmd_name="H"))
    if name == "SynchrotronConstant":
        return SynchrotronConstant(photon_species=_ELECTRON)
    if name == "SynchrotronParams":
        return SynchrotronParams()
    if name == "NoCurrent":
        return NoCurrent()
    if name == "BSI":
        return BSI(ionization_current=NoCurrent(), ionization_electron_species=_ELECTRON)
    if name == "BSIEffectiveZ":
        return BSIEffectiveZ(ionization_current=NoCurrent(), ionization_electron_species=_ELECTRON)
    if name == "BSIStarkShifted":
        return BSIStarkShifted(ionization_current=NoCurrent(), ionization_electron_species=_ELECTRON)
    if name == "ADKLinearPolarization":
        return ADKLinearPolarization(ionization_current=NoCurrent(), ionization_electron_species=_ELECTRON)
    if name == "ADKCircularPolarization":
        return ADKCircularPolarization(ionization_current=NoCurrent(), ionization_electron_species=_ELECTRON)
    if name == "Keldysh":
        return Keldysh(ionization_current=NoCurrent(), ionization_electron_species=_ELECTRON)
    if name == "ThomasFermi":
        return ThomasFermi(ionization_electron_species=_ELECTRON)
    if name == "GroundStateIonization":
        return GroundStateIonization(
            ionization_model_list=[
                BSI(ionization_current=NoCurrent(), ionization_electron_species=_ELECTRON),
                ADKLinearPolarization(ionization_current=NoCurrent(), ionization_electron_species=_ELECTRON),
                ThomasFermi(ionization_electron_species=_ELECTRON),
            ]
        )
    if name == "SimpleDensity":
        return SimpleDensity(profile=Uniform(density_si=42.0), species=[_ELECTRON, _ION], layout=Random(ppc=4))
    if name == "SimpleMomentum":
        return SimpleMomentum(
            species=_ELECTRON, temperature=Temperature(temperature_kev=1e4), drift=Drift.from_velocity((1e5, 0, 0))
        )
    if name == "SetChargeState":
        return SetChargeState(species=_ION, charge_state=1)
    if name == "Uniform":
        return Uniform(density_si=42.0)
    if name == "Foil":
        return Foil(density_si=42.0, y_value_front_foil_si=0.0, thickness_foil_si=1e-6)
    if name == "Gaussian_profile":
        return Gaussian(
            center_front=0.0,
            center_rear=1e-6,
            sigma_front=1e-7,
            sigma_rear=1e-7,
            factor=-1.0,
            power=2.0,
            vacuum_cells_front=0,
            density=42.0,
        )
    if name == "Cylinder":
        return Cylinder(
            density_si=42.0,
            radius_si=1e-6,
            center_position_si=(0.0, 0.5, 0.5),
            cylinder_axis=(0.0, 1.0, 0.0),
        )
    if name == "FreeFormula":
        return FreeFormula(density_expression="x")
    if name == "Exponential_ramp":
        return Exponential(PlasmaLength=1e-6, PlasmaCutoff=0.0)
    if name == "Random":
        return Random(ppc=4)
    if name == "Quiet":
        return Quiet(ppc=8, n_points=(2, 2, 2))
    if name == "OnePosition":
        return OnePosition(ppc=2, in_cell_offset=(0.5, 0.5, 0.5))
    if name == "Drift":
        return Drift.from_velocity((1e5, 0, 0))
    if name == "Temperature_kev":
        return Temperature(temperature_kev=1e4)
    if name == "Temperature_directional":
        return Temperature(temperature_kev_directional=(1.0, 2.0, 3.0))
    if name == "CustomUserInput":
        cu = CustomUserInput()
        cu.addToCustomInput({"test_data_1": 1}, "tag_1")
        return cu
    raise AssertionError(f"unknown round-trip candidate {name=}")


_MODELS = [
    # grid / window / time
    "Grid3D",
    "Walltime",
    "MovingWindow",
    "Spec_full",
    "Spec_opt",
    "TimeStepSpec",
    # solvers
    "YeeSolver",
    "LeheSolver",
    # lasers
    "GaussianLaser",
    "PlaneWaveLaser",
    "DispersivePulseLaser",
    "TWTSLaser",
    "FromOpenPMDPulseLaser",
    # radiation
    "LinearFrequencies",
    "LogFrequencies",
    "RadiationObserverConfiguration",
    "RadiationObserverConfiguration_nonunit",
    "RadiationConfiguration",
    "RadiationPluginConfig",
    "RadiationPlugin",
    # plugins / diagnostics
    "Checkpoint",
    "Checkpoint_timePeriod",
    "PhaseSpace",
    "EnergyHistogram",
    "FieldDump_native",
    "ParticleFunctor",
    "ParticleFunctor_rng",
    "FieldDump_derived",
    "FilteredSpecies",
    "OpenPMDConfig",
    "RangeSpec",
    "OpenPMDPlugin",
    "BinSpec",
    "BinningAxis",
    "Binning",
    # collisions
    "ConstLogCollision",
    "DynamicLogCollision",
    "Collision",
    "Collision_filters",
    "CollisionNumericsConfig",
    "CollisionalPhysicsSetup",
    # species / attributes / constants
    "Species",
    "Species_ion",
    "Position",
    "Weighting",
    "Momentum",
    "BoundElectrons",
    "Mass",
    "Charge",
    "DensityRatio",
    "Element",
    "Element_isotope",
    "ElementProperties",
    "SynchrotronConstant",
    "SynchrotronParams",
    "NoCurrent",
    # ionization models
    "BSI",
    "BSIEffectiveZ",
    "BSIStarkShifted",
    "ADKLinearPolarization",
    "ADKCircularPolarization",
    "Keldysh",
    "ThomasFermi",
    "GroundStateIonization",
    # operations
    "SimpleDensity",
    "SimpleMomentum",
    "SetChargeState",
    "Uniform",
    "Foil",
    "Gaussian_profile",
    "Cylinder",
    "FreeFormula",
    "Exponential_ramp",
    "Random",
    "Quiet",
    "OnePosition",
    "Drift",
    "Temperature_kev",
    "Temperature_directional",
    # custom user input
    "CustomUserInput",
]


@pytest.mark.parametrize("name", _MODELS)
def test_model_roundtrip(name):
    model = _build(name)
    dumped = model.model_dump(mode="json")
    # the canonical reconstruction path: rebuild from the serialised JSON
    restored = type(model).model_validate(dumped)
    assert isinstance(restored, type(model)), f"{name} did not reconstruct to its own type: {type(restored).__name__}"
    assert restored.model_dump(mode="json") == dumped, f"{name} does not round-trip through model_dump(mode='json')"


def _representative_sim():
    grid = picmi.Cartesian3DGrid(
        number_of_cells=[16, 16, 16],
        lower_bound=[0, 0, 0],
        upper_bound=[1e-5, 1e-5, 1e-5],
        lower_boundary_conditions=["periodic", "periodic", "periodic"],
        upper_boundary_conditions=["periodic", "periodic", "periodic"],
    )
    solver = picmi.ElectromagneticSolver(method="Yee", grid=grid)
    sim = picmi.Simulation(time_step_size=1e-15, max_steps=100, solver=solver)

    profile = picmi.UniformDistribution(density=42, rms_velocity=[1e5, 0, 0], directed_velocity=[1e5, 0, 0])
    sim.add_species(
        picmi.Species(name="electron", mass=9.109e-31, charge=-1.602e-19, initial_distribution=profile),
        picmi.PseudoRandomLayout(n_macroparticles_per_cell=4),
    )
    sim.add_species(
        picmi.Species(name="ion", mass=1.67e-27, charge=1.602e-19, initial_distribution=profile),
        picmi.PseudoRandomLayout(n_macroparticles_per_cell=2),
    )

    laser = picmi.GaussianLaser(
        wavelength=0.8e-6,
        waist=1e-5,
        duration=1e-15,
        focal_position=[0.5e-5, 0.5e-5, 0.5e-5],
        centroid_position=[0.5e-5, -0.5e-5, 0.5e-5],
        propagation_direction=[0.0, 1.0, 0.0],
        polarization_direction=[0.0, 0.0, 1.0],
        E0=1e10,
        phi0=0.0,
        picongpu_huygens_surface_positions=[[1, -1], [1, -1], [1, -1]],
    )
    sim.add_laser(laser, None)

    from picongpu.picmi.diagnostics import Checkpoint, PhaseSpace, TimeStepSpec

    sim.add_diagnostic(
        PhaseSpace(
            species=sim.species[0],
            period=TimeStepSpec[::10]("steps"),
            spatial_coordinate="x",
            momentum_coordinate="px",
            min_momentum=-1,
            max_momentum=1,
        )
    )
    sim.add_diagnostic(Checkpoint(period=TimeStepSpec[::50]("steps")))
    return sim


def test_simulation_roundtrips_from_rendering_context():
    # the rendering context stored during generate() is the serialised form of
    # the Simulation; it must be validatable again and re-serialise identically
    sim = _representative_sim()
    with tempfile.TemporaryDirectory() as tmp:
        setup = Path(tmp) / "setup"
        sim.write_input_file(setup)
        context = json.loads((setup / "metadata" / "pypicongpu_rendering_context.json").read_text())

    restored = Simulation.model_validate(context)
    assert restored.model_dump(mode="json") == context, "Simulation does not round-trip through the rendering context"


def test_runner_roundtrips_from_runner_metadata():
    # the runner metadata stored during generate() must be validatable again,
    # yielding a Runner whose simulation is a proper pypicongpu Simulation
    sim = _representative_sim()
    with tempfile.TemporaryDirectory() as tmp:
        setup = Path(tmp) / "setup"
        sim.write_input_file(setup)
        runner_json = json.loads((setup / "metadata" / "pypicongpu_runner.json").read_text())

    restored = Runner.model_validate(runner_json)
    assert isinstance(restored, Runner)
    assert isinstance(restored.sim, Simulation)
    # the re-serialisation contract: the reconstructed runner must dump
    # identically to the on-disk metadata (same as the Simulation counterpart)
    assert restored.model_dump(mode="json") == runner_json


def _collision_sim():
    # a representative simulation whose collisional physics carries a real
    # (constant-log) collision, built through the picmi interaction API
    grid = picmi.Cartesian3DGrid(
        number_of_cells=[16, 16, 16],
        lower_bound=[0, 0, 0],
        upper_bound=[1e-5, 1e-5, 1e-5],
        lower_boundary_conditions=["periodic", "periodic", "periodic"],
        upper_boundary_conditions=["periodic", "periodic", "periodic"],
    )
    solver = picmi.ElectromagneticSolver(method="Yee", grid=grid)
    sim = picmi.Simulation(time_step_size=1e-15, max_steps=100, solver=solver)

    profile = picmi.UniformDistribution(density=42, rms_velocity=[1e5, 0, 0], directed_velocity=[1e5, 0, 0])
    electron = picmi.Species(name="electron", mass=9.109e-31, charge=-1.602e-19, initial_distribution=profile)
    hydrogen = picmi.Species(name="hydrogen", mass=1.67e-27, charge=1.602e-19, initial_distribution=profile)
    sim.add_species(electron, picmi.PseudoRandomLayout(n_macroparticles_per_cell=4))
    sim.add_species(hydrogen, picmi.PseudoRandomLayout(n_macroparticles_per_cell=2))

    sim.picongpu_interaction = [
        PicmiCollisionalPhysicsSetup(
            collisions=[
                PicmiCollision(species_pairs=[(electron, hydrogen)], functor=picmi.ConstLogCollision(coulomb_log=12.0))
            ]
        )
    ]
    return sim


def _assert_same_tree(a: Path, b: Path):
    files_a = {p.relative_to(a) for p in a.rglob("*") if p.is_file()}
    files_b = {p.relative_to(b) for p in b.rglob("*") if p.is_file()}
    assert files_a == files_b, f"file sets differ between {a} and {b}: {files_a ^ files_b}"
    for rel in files_a:
        assert (a / rel).read_bytes() == (b / rel).read_bytes(), f"rendered file differs: {rel}"


def test_collision_setup_roundtrips_and_renders_identically():
    # end-to-end collision regression: a setup containing a real collision must
    # generate at all (the rendering-context schema check used to reject the
    # serialised species_pairs shape before any artifact was written), both
    # metadata JSONs must reload into re-serialising-identical instances, and a
    # regeneration from the reconstructed simulation must render a
    # byte-identical include/ + etc/ tree
    sim = _collision_sim()
    with tempfile.TemporaryDirectory() as tmp:
        setup = Path(tmp) / "setup"
        sim.write_input_file(setup)
        context = json.loads((setup / "metadata" / "pypicongpu_rendering_context.json").read_text())
        runner_json = json.loads((setup / "metadata" / "pypicongpu_runner.json").read_text())

        restored_sim = Simulation.model_validate(context)
        assert restored_sim.model_dump(mode="json") == context

        restored_runner = Runner.model_validate(runner_json)
        assert isinstance(restored_runner, Runner)
        assert isinstance(restored_runner.sim, Simulation)
        assert restored_runner.model_dump(mode="json") == runner_json

        setup2 = Path(tmp) / "setup2"
        Runner(sim=restored_sim, setup_dir=setup2, run_dir=Path(tmp) / "run2").generate()
        _assert_same_tree(setup / "include", setup2 / "include")
        _assert_same_tree(setup / "etc", setup2 / "etc")


def test_collision_functor_malformed_dict_raises_value_error():
    # a malformed serialised functor (type_constlog without data.coulomb_log)
    # must fail with a validation-style error, not a raw KeyError
    with pytest.raises(ValueError, match="data.coulomb_log"):
        Collision(species_pairs=[(_ELECTRON, _ELECTRON)], functor={"type_constlog": True, "data": {}})


def test_radiation_observer_user_index_symbol_not_conflated():
    # a user direction that uses its own symbol named "index" as a constant
    # must not be conflated with the observer index: the canonical
    # serialisation placeholder is mangled, so the user constant survives
    # the round-trip as a free symbol (n1)
    tilt = Symbol("index")
    model = RadiationObserverConfiguration(index_to_direction=lambda i: (tilt + i, 1, 0), N_observer=4)
    dumped = model.model_dump(mode="json")
    restored = RadiationObserverConfiguration.model_validate(dumped)
    assert restored.model_dump(mode="json") == dumped
    x, y, z = restored.index_to_direction(0)
    assert x.free_symbols == {tilt}, f"user constant lost in round-trip: {x}"


def test_radiation_observer_nonunit_direction_roundtrips():
    # a direction whose magnitude is not symbolically 1 goes through the
    # validator's normalising branch; the reconstructed mapping must still be
    # unit-length and point along the original direction
    model = RadiationObserverConfiguration(index_to_direction=lambda i: (i, 1, 0), N_observer=8)
    dumped = model.model_dump(mode="json")
    restored = RadiationObserverConfiguration.model_validate(dumped)
    assert restored.model_dump(mode="json") == dumped
    for k in (3, 7):
        x, y, z = restored.index_to_direction(k)
        assert x**2 + y**2 + z**2 == 1
        assert x / y == k
        assert z == 0
