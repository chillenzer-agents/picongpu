"""
This file is part of PIConGPU.
Copyright 2021-2026 PIConGPU contributors
Authors: Hannes Troepgen, Brian Edward Marre, Richard Pausch, Julian Lenz
License: GPLv3+
"""

import copy
import os
import shutil
import tempfile
import warnings
from pathlib import Path
from unittest import TestCase

import pytest
from pydantic import ValidationError
from picongpu import picmi
from picongpu.picmi.interaction.ionization.fieldionization import ADK, ADKVariant
from picongpu.pypicongpu import customuserinput, species


def get_grid(delta_x: float, delta_y: float, delta_z: float, n: int):
    # sets delta_[x,y,z] implicitly by providing bounding box+cell count
    return picmi.Cartesian3DGrid(
        number_of_cells=[n, n, n],
        lower_bound=[0, 0, 0],
        upper_bound=list(map(lambda x: n * x, [delta_x, delta_y, delta_z])),
        # required, otherwise won't spawn
        lower_boundary_conditions=["open", "open", "periodic"],
        upper_boundary_conditions=["open", "open", "periodic"],
    )


def get_sim_cfl_helper(
    delta_t: float | None,
    cfl: float | None,
    delta_3d: tuple[float, float, float],
    method: str,
    n: int = 100,
) -> picmi.Simulation:
    grid = get_grid(delta_3d[0], delta_3d[1], delta_3d[2], n)
    solver = picmi.ElectromagneticSolver(method=method, grid=grid, cfl=cfl)
    return picmi.Simulation(time_step_size=delta_t, solver=solver)


class TestPicmiSimulation(TestCase):
    def __get_sim(self):
        grid = get_grid(1, 1, 1, 32)
        solver = picmi.ElectromagneticSolver(method="Yee", grid=grid)
        sim = picmi.Simulation(time_step_size=17, max_steps=4, solver=solver)

        return sim

    def __get_tmpdir_name(self):
        """
        get name of non-existing tmp dir which will be automatically cleaned up
        """
        name = None
        with tempfile.TemporaryDirectory() as tmpdir:
            name = tmpdir
        assert not os.path.exists(name)
        self.__to_cleanup.append(name)
        return name

    def setUp(self):
        self.sim = self.__get_sim()
        self.layout = picmi.PseudoRandomLayout(n_macroparticles_per_cell=2)
        self.__to_cleanup = []

        self.customData_1 = [{"test_data_1": 1}, "tag_1"]
        self.customData_2 = [{"test_data_2": 2}, "tag_2"]

    def tearDown(self):
        for dir_to_cleanup in self.__to_cleanup:
            if os.path.isdir(dir_to_cleanup):
                shutil.rmtree(dir_to_cleanup)
            assert not os.path.exists(dir_to_cleanup)

    def test_cfl_yee(self):
        # the Courant-Friedrichs-Lewy condition describes the relationship
        # between delta_t, delta_[x,y,z] and a parameter, here "cfl"
        # notably, all three can be given explicitly, though only two of the
        # three are required.
        # for practical reasons, delta_[x,y,z] has to be provided
        # this test checks the proper calculation of the cfl/delta_t

        # nothing defined if grid is empty
        sim = picmi.Simulation()
        assert sim.time_step_size is None
        sim = picmi.Simulation(time_step_size=17)
        assert sim.time_step_size == 17

        # delta_t = cfl = None -> ignored (at least during instantiation;
        # can throw later)
        get_sim_cfl_helper(None, None, (1, 1, 1), "Yee")

        # delta_t -> cfl
        sim = get_sim_cfl_helper(2.02760320328617635877e-13, None, (7e-6, 8e-6, 9e-6), "Yee")
        assert abs(sim.solver.cfl - 13.37) < 1e-10

        # cfl -> delta_t
        sim = get_sim_cfl_helper(None, 0.99, (3, 4, 5), "Yee")
        assert abs(sim.time_step_size - 7.14500557764070900528e-9) < 1e-20

        # both delta_t and cfl defined:
        # case a: silently pass if they do match
        get_sim_cfl_helper(7.14500557764070900528e-9, 0.99, (3, 4, 5), "Yee")

        # case b: raise error if no match
        with pytest.raises(ValueError):
            # delta_t does not match cfl at all
            get_sim_cfl_helper(1, 0.99, (3, 4, 5), "Yee")

    def test_species_translation(self):
        """test that species are moved to PyPIConGPU simulation"""
        grid = get_grid(1, 1, 1, 64)
        solver = picmi.ElectromagneticSolver(method="Yee", grid=grid)
        sim = picmi.Simulation(time_step_size=17, max_steps=4, solver=solver)

        profile = picmi.UniformDistribution(density=42)
        layout3 = picmi.PseudoRandomLayout(n_macroparticles_per_cell=3)
        layout4 = picmi.PseudoRandomLayout(n_macroparticles_per_cell=4)

        # species list empty by default
        assert sim.get_as_pypicongpu().species == []

        # not placed
        sim.add_species(picmi.Species(name="dummy1", mass=5), None)

        # placed with entire placement and 3ppc
        sim.add_species(picmi.Species(name="dummy2", mass=3, density_scale=4, initial_distribution=profile), layout3)

        # placed with default ratio of 1 and 4ppc
        sim.add_species(picmi.Species(name="dummy3", mass=3, initial_distribution=profile), layout4)

        picongpu = sim.get_as_pypicongpu()
        assert len(picongpu.species) == 3
        species_names = set(map(lambda species: species.name, picongpu.species))
        assert species_names == {"dummy1", "dummy2", "dummy3"}

        # check typical ppc is derived
        assert picongpu.typical_ppc == 3

    def test_explicit_typical_ppc(self):
        grid = get_grid(1, 1, 1, 64)
        solver = picmi.ElectromagneticSolver(method="Yee", grid=grid)
        sim = picmi.Simulation(time_step_size=17, max_steps=4, solver=solver, picongpu_typical_ppc=15)

        profile = picmi.UniformDistribution(density=42)
        layout3 = picmi.PseudoRandomLayout(n_macroparticles_per_cell=3)
        layout4 = picmi.PseudoRandomLayout(n_macroparticles_per_cell=4)

        # placed with entire placement and 3ppc
        sim.add_species(
            picmi.Species(name="dummy2", mass=3, charge=4, density_scale=4, initial_distribution=profile), layout3
        )
        # placed with default ratio of 1 and 4ppc
        sim.add_species(picmi.Species(name="dummy3", mass=3, charge=4, initial_distribution=profile), layout4)

        picongpu = sim.get_as_pypicongpu()
        assert len(picongpu.species) == 2
        species_names = set(map(lambda species: species.name, picongpu.species))
        assert species_names == {"dummy2", "dummy3"}

        # check explicitly set typical ppc is respected
        assert picongpu.typical_ppc == 15

    def test_wrong_explicitly_set_typical_ppc(self):
        grid = get_grid(1, 1, 1, 64)
        solver = picmi.ElectromagneticSolver(method="Yee", grid=grid)

        wrongValues = [0, -1, -15]
        for value in wrongValues:
            with pytest.raises(ValueError, match="Typical ppc should be > 0"):
                picmi.Simulation(time_step_size=17, max_steps=4, solver=solver, picongpu_typical_ppc=value)

        wrongTypes = [0.0, -1.0, -15.0]
        for value in wrongTypes:
            with pytest.raises(ValueError, match="Typical ppc should be > 0"):
                picmi.Simulation(time_step_size=17, max_steps=4, solver=solver, picongpu_typical_ppc=value)

    def test_invalid_placement(self):
        profile = picmi.UniformDistribution(density=42)
        layout = picmi.PseudoRandomLayout(n_macroparticles_per_cell=3)

        # both profile and layout must be given
        with pytest.raises(Exception, match=".*initial.*distribution.*"):
            # no profile
            sim = copy.deepcopy(self.sim)
            sim.add_species(picmi.Species(name="dummy3"), layout)
            sim.get_as_pypicongpu()
        with pytest.raises(Exception, match=".*layout.*"):
            # no layout
            sim = copy.deepcopy(self.sim)
            sim.add_species(picmi.Species(name="dummy3", initial_distribution=profile), None)
            sim.get_as_pypicongpu()

        with pytest.raises(Exception, match=".*initial.*distribution.*"):
            # neither profile nor layout, but ratio
            sim = copy.deepcopy(self.sim)
            sim.add_species(picmi.Species(name="dummy3", density_scale=7), None)
            sim.get_as_pypicongpu()

    def test_operations_simple_density_translated(self):
        """simple density operations are correctly derived

        Species are initialised independently by default (picmi-standard
        semantics, Option B): only members of the same explicit MultiSpecies
        share a density operation (collective initialisation), everything else
        is split into individual operations.
        """
        profile = picmi.UniformDistribution(density=42)
        other_profile = picmi.UniformDistribution(density=17)
        layout = picmi.PseudoRandomLayout(n_macroparticles_per_cell=3)
        other_layout = picmi.PseudoRandomLayout(n_macroparticles_per_cell=4)

        # explicitly coordinated group
        multispecies = picmi.MultiSpecies(
            particle_types=["electron", "H"],
            names=["colocated1", "colocated2"],
            proportions=[4, 2],
            initial_distribution=profile,
        )
        self.sim.add_species(multispecies[0], layout)
        self.sim.add_species(multispecies[1], layout)
        # independent species that merely look the same w.r.t. profile/layout
        self.sim.add_species(
            picmi.Species(name="separate1", mass=3, initial_distribution=other_profile),
            layout,
        )
        self.sim.add_species(
            picmi.Species(name="separate2", mass=4, initial_distribution=profile),
            other_layout,
        )

        pypic = self.sim.get_as_pypicongpu()
        my_species = pypic.species
        operations = pypic.init_operations

        # species
        assert len(my_species) == 4
        assert ["colocated1", "colocated2", "separate1", "separate2"] == list(
            map(lambda species: species.name, my_species)
        )

        # operations
        density_operations = list(
            filter(
                lambda op: isinstance(op, species.operation.SimpleDensity),
                operations,
            )
        )
        assert len(density_operations) == 3
        for op in density_operations:
            assert isinstance(op.profile, species.operation.densityprofile.Uniform)

            species_names = set(map(lambda species: species.name, op.species))

            # ensure grouping:
            if "separate1" in species_names or "separate2" in species_names:
                # one of the two lone species (no MultiSpecies -> independent)
                assert len(species_names) == 1
            else:
                # the two colocated species (explicit MultiSpecies)
                assert len(species_names) == 2

            # check profile
            if "separate2" in species_names or "colocated1" in species_names:
                # used "profile"
                assert op.profile.density_si == 42
            else:
                # used "other_profile"
                assert op.profile.density_si == 17

            # check layout
            if "separate1" in species_names or "colocated1" in species_names:
                # used "layout"
                assert op.layout.ppc == 3
            else:
                # used "other_layout"
                assert op.layout.ppc == 4

    def test_simple_density_independent_by_default(self):
        """same distribution+layout no longer merges implicitly (Option B)"""
        profile = picmi.UniformDistribution(density=42)
        layout = picmi.PseudoRandomLayout(n_macroparticles_per_cell=3)
        for name in ("electron_1", "electron_2"):
            self.sim.add_species(
                picmi.Species(name=name, particle_type="electron", initial_distribution=profile), layout
            )

        with pytest.warns(UserWarning, match="MultiSpecies"):
            density_operations = list(
                filter(
                    lambda op: isinstance(op, species.operation.SimpleDensity),
                    self.sim.get_as_pypicongpu().init_operations,
                )
            )
        assert len(density_operations) == 2

    def test_removed_implicit_merge_heuristic_warns(self):
        """species that the old implicit-derive heuristic WOULD have merged now warn loudly"""
        profile = picmi.UniformDistribution(density=42)
        layout = picmi.PseudoRandomLayout(n_macroparticles_per_cell=3)

        # (a) two plain look-alike species -> one loud UserWarning, still independent
        self.sim.add_species(picmi.Species(name="e1", particle_type="electron", initial_distribution=profile), layout)
        self.sim.add_species(picmi.Species(name="e2", particle_type="electron", initial_distribution=profile), layout)
        with pytest.warns(UserWarning, match="e1"):
            ops = self.sim.get_as_pypicongpu().init_operations
        assert len([op for op in ops if isinstance(op, species.operation.SimpleDensity)]) == 2

        # (b) an explicit MultiSpecies of the same look-alike species -> no warning
        sim = self.__get_sim()
        multispecies = picmi.MultiSpecies(
            particle_types=["electron", "electron"],
            names=["m1", "m2"],
            proportions=[1.0, 1.0],
            initial_distribution=profile,
        )
        sim.add_species(multispecies[0], layout)
        sim.add_species(multispecies[1], layout)
        with warnings.catch_warnings():
            warnings.simplefilter("error", UserWarning)
            sim.get_as_pypicongpu()

    def test_removed_implicit_merge_heuristic_no_warning_on_differing_layout(self):
        """species with the same profile but different layouts never warned (never merged before)"""
        profile = picmi.UniformDistribution(density=42)
        self.sim.add_species(
            picmi.Species(name="e1", particle_type="electron", initial_distribution=profile),
            picmi.PseudoRandomLayout(n_macroparticles_per_cell=3),
        )
        self.sim.add_species(
            picmi.Species(name="e2", particle_type="electron", initial_distribution=profile),
            picmi.PseudoRandomLayout(n_macroparticles_per_cell=4),
        )
        with warnings.catch_warnings():
            warnings.simplefilter("error", UserWarning)
            self.sim.get_as_pypicongpu()

    def test_multispecies_three_members_one_created_two_derived(self):
        """#5762 shape: 3 members, same density but differing momentum -> 1 created + 2 derived"""
        base_profile = picmi.UniformDistribution(density=42)
        momenta = [
            picmi.UniformDistribution(density=42, rms_velocity=[0.0, 0.0, 0.0]),
            picmi.UniformDistribution(density=42, rms_velocity=[1.0e6, 1.0e6, 1.0e6]),
            picmi.UniformDistribution(density=42, rms_velocity=[2.0e6, 1.0e6, 5.0e5]),
        ]
        layout = picmi.PseudoRandomLayout(n_macroparticles_per_cell=4)
        multispecies = picmi.MultiSpecies(
            particle_types=["electron", "H", "He"],
            names=["a", "b", "c"],
            proportions=[1.0, 1.0, 1.0],
            initial_distribution=base_profile,
        )
        for member, distribution in zip(multispecies, momenta, strict=True):
            member.initial_distribution = distribution
            self.sim.add_species(member, layout)

        density_operations = list(
            filter(
                lambda op: isinstance(op, species.operation.SimpleDensity),
                self.sim.get_as_pypicongpu().init_operations,
            )
        )
        # exactly ONE CreateDensity placing the *single* created species...
        assert len(density_operations) == 1
        op = density_operations[0]
        assert isinstance(op.placed_species_initial, species.Species)
        assert len(op.placed_species_copied) == 2
        # ... plus per-species momentum (SimpleMomentum) for all three members
        momentum_operations = list(
            filter(
                lambda op_: isinstance(op_, species.operation.SimpleMomentum),
                self.sim.get_as_pypicongpu().init_operations,
            )
        )
        assert len(momentum_operations) == 3

    def test_multispecies_marker_not_serialized(self):
        """the _multi_species grouping marker is not part of the serialized species (documented limitation)"""
        profile = picmi.UniformDistribution(density=42)
        multispecies = picmi.MultiSpecies(
            particle_types=["electron", "H"],
            names=["electron", "proton"],
            proportions=[1.0, 1.0],
            initial_distribution=profile,
        )
        assert multispecies[0]._multi_species is not None
        # the marker is a PrivateAttr and hence never part of model_dump()
        assert "_multi_species" not in multispecies[0].model_dump()

    def test_multispecies_members_and_density_ratio(self):
        """MultiSpecies members share one distribution and map proportions to DensityRatio"""
        profile = picmi.UniformDistribution(density=42)
        layout = picmi.PseudoRandomLayout(n_macroparticles_per_cell=8)
        multispecies = picmi.MultiSpecies(
            particle_types=["electron", "H"],
            names=["electron", "proton"],
            proportions=[1.0, 2.0],
            initial_distribution=profile,
        )
        assert len(multispecies) == 2

        for member, proportion in zip(multispecies, [1.0, 2.0], strict=True):
            # plain picmi species sharing the distribution
            assert isinstance(member, picmi.Species)
            assert member.initial_distribution is profile
            assert member.density_scale == proportion
            # density_scale maps to DensityRatio on the pypicongpu level
            assert member._evaluate_species_requirements()["constants"] and any(
                ratio.ratio == proportion
                for ratio in member._evaluate_species_requirements()["constants"]
                if hasattr(ratio, "ratio")
            )

        # the whole MultiSpecies is placed on a single shared grid
        for layout_member in multispecies.species_instances_list:
            self.sim.add_species(layout_member, layout)

        density_operations = list(
            filter(
                lambda op: isinstance(op, species.operation.SimpleDensity),
                self.sim.get_as_pypicongpu().init_operations,
            )
        )
        assert len(density_operations) == 1
        op = density_operations[0]
        # exactly one species is created ("placed"), the other one is derived
        assert len(op.placed_species_copied) == 1
        assert set(s.name for s in op.species) == {"electron", "proton"}

    def test_multispecies_same_density_different_momentum_charge_neutral(self):
        """#5762: same density, differing momentum -> grouped (charge-neutral)"""
        # density distribution common to all members, different momenta per member
        base_profile = picmi.UniformDistribution(density=42)
        profile_cold = picmi.UniformDistribution(density=42, rms_velocity=[0.0, 0.0, 0.0])
        profile_hot = picmi.UniformDistribution(density=42, rms_velocity=[1.0e6, 1.0e6, 1.0e6])
        layout = picmi.PseudoRandomLayout(n_macroparticles_per_cell=4)
        multispecies = picmi.MultiSpecies(
            particle_types=["electron", "H"],
            names=["colder", "hotter"],
            proportions=[1.0, 1.0],
            initial_distribution=base_profile,
        )
        # customize the momentum (rms_velocity) per member while keeping the density
        multispecies[0].initial_distribution = profile_cold
        multispecies[1].initial_distribution = profile_hot
        for member in multispecies:
            self.sim.add_species(member, layout)

        pypic = self.sim.get_as_pypicongpu()
        density_operations = list(
            filter(
                lambda op: isinstance(op, species.operation.SimpleDensity),
                pypic.init_operations,
            )
        )
        momentum_operations = list(
            filter(
                lambda op: isinstance(op, species.operation.SimpleMomentum),
                pypic.init_operations,
            )
        )
        # differing momentum must NOT prevent collective (charge-neutral) init:
        # one density op placing both species on identical in-cell positions...
        assert len(density_operations) == 1
        assert len(density_operations[0].species) == 2
        # ... while momentum is still applied individually per species
        assert len(momentum_operations) == 2

    def test_multispecies_different_seed_independent(self):
        """same density + different random-layout seed -> independent (non-neutral on purpose)"""
        profile = picmi.UniformDistribution(density=42)
        layout_a = picmi.PseudoRandomLayout(n_macroparticles_per_cell=4, seed=1)
        layout_b = picmi.PseudoRandomLayout(n_macroparticles_per_cell=4, seed=2)
        multispecies = picmi.MultiSpecies(
            particle_types=["electron", "H"],
            names=["electron", "proton"],
            proportions=[1.0, 1.0],
            initial_distribution=profile,
        )
        self.sim.add_species(multispecies[0], layout_a)
        self.sim.add_species(multispecies[1], layout_b)

        density_operations = list(
            filter(
                lambda op: isinstance(op, species.operation.SimpleDensity),
                self.sim.get_as_pypicongpu().init_operations,
            )
        )
        # different seeds force independent initialisation
        assert len(density_operations) == 2

    def test_random_layout_seed_discriminator(self):
        """the pseudo-random layout seed is a force-independent discriminator"""
        profile = picmi.UniformDistribution(density=42)
        seeded = picmi.PseudoRandomLayout(n_macroparticles_per_cell=4, seed=42)
        unseeded = picmi.PseudoRandomLayout(n_macroparticles_per_cell=4)
        # the seed is no longer swallowed on the picmi level
        assert seeded.seed == 42
        assert unseeded.seed is None
        # ... and forwarded to the pypicongpu random layout
        assert seeded.get_as_pypicongpu().seed == 42
        # equal-ppc random layouts with different seeds compare unequal (not merged)
        assert seeded.get_as_pypicongpu() != unseeded.get_as_pypicongpu()
        assert (
            seeded.get_as_pypicongpu()
            == picmi.PseudoRandomLayout(n_macroparticles_per_cell=4, seed=42).get_as_pypicongpu()
        )

        # even inside a MultiSpecies different seeds prevent merging
        multispecies = picmi.MultiSpecies(
            particle_types=["electron", "H"],
            names=["electron", "proton"],
            proportions=[1.0, 1.0],
            initial_distribution=profile,
        )
        self.sim.add_species(multispecies[0], seeded)
        self.sim.add_species(multispecies[1], unseeded)
        density_operations = list(
            filter(
                lambda op: isinstance(op, species.operation.SimpleDensity),
                self.sim.get_as_pypicongpu().init_operations,
            )
        )
        assert len(density_operations) == 2

    def test_random_layout_seed_does_not_change_rendered_cpp(self):
        """a lone seeded PseudoRandomLayout renders byte-identically to seed=None (seed is grouping-only)"""
        profile = picmi.UniformDistribution(density=42)

        def render(seed):
            grid = get_grid(1, 1, 1, 8)
            solver = picmi.ElectromagneticSolver(method="Yee", grid=grid)
            sim = picmi.Simulation(time_step_size=17, max_steps=1, solver=solver)
            layout = picmi.PseudoRandomLayout(n_macroparticles_per_cell=2, seed=seed)
            sim.add_species(
                picmi.Species(name="electron", particle_type="electron", initial_distribution=profile), layout
            )
            outdir = self.__get_tmpdir_name()
            sim.write_input_file(outdir)
            return outdir

        seeded_dir = render(42)
        unseeded_dir = render(None)

        def cpp_relative_files(root):
            include_root = os.path.join(root, "include")
            return {
                os.path.relpath(os.path.join(dp, f), root): None
                for dp, _, names in os.walk(include_root)
                for f in names
            }

        seeded_files = cpp_relative_files(seeded_dir)
        unseeded_files = cpp_relative_files(unseeded_dir)
        assert set(seeded_files) == set(unseeded_files)
        for rel in seeded_files:
            with open(os.path.join(seeded_dir, rel), "rb") as lhs, open(os.path.join(unseeded_dir, rel), "rb") as rhs:
                assert lhs.read() == rhs.read(), f"rendered C++ differs for {rel}: seed must not reach the C++ output"

    def test_multispecies_grouping_survives_deepcopy(self):
        """explicit MultiSpecies grouping survives a simulation round-trip (deepcopy)"""
        profile = picmi.UniformDistribution(density=42)
        layout = picmi.PseudoRandomLayout(n_macroparticles_per_cell=4)
        multispecies = picmi.MultiSpecies(
            particle_types=["electron", "H"],
            names=["electron", "proton"],
            proportions=[1.0, 1.0],
            initial_distribution=profile,
        )
        for member in multispecies:
            self.sim.add_species(member, layout)

        sim_copy = copy.deepcopy(self.sim)
        density_operations = list(
            filter(
                lambda op: isinstance(op, species.operation.SimpleDensity),
                sim_copy.get_as_pypicongpu().init_operations,
            )
        )
        # grouping must survive the copy, i.e. the two members still share one op
        assert len(density_operations) == 1
        assert len(density_operations[0].species) == 2

    def test_operation_not_placed_translated(self):
        """non-placed species are correctly translated"""
        self.sim.add_species(picmi.Species(name="notplaced", mass=1, initial_distribution=None), None)

        pypicongpu = self.sim.get_as_pypicongpu()

        assert len(pypicongpu.species) == 1
        # not placed, momentum (both initialize to empty)
        assert len(pypicongpu.init_operations) == 0

    def test_operation_momentum(self):
        """operation for momentum correctly derived from species"""
        self.sim.add_species(
            picmi.Species(
                name="valid",
                mass=17,
                initial_distribution=picmi.UniformDistribution(
                    density=17,
                    rms_velocity=[17, 17, 17],
                    directed_velocity=[31283745.0, 45132121.0, 215484563.0],
                ),
            ),
            picmi.PseudoRandomLayout(n_macroparticles_per_cell=2),
        )

        pypicongpu = self.sim.get_as_pypicongpu()

        mom_ops = list(
            filter(
                lambda op: isinstance(op, species.operation.SimpleMomentum),
                pypicongpu.init_operations,
            )
        )

        # momentum operation must always be generated
        assert len(mom_ops) == 1
        mom_op = mom_ops[0]

        assert mom_op.species.name == "valid"
        assert abs(mom_op.temperature.temperature_kev - 3.06645343e19) < 1e13
        assert mom_op.drift.direction_normalized == (
            0.14068221552237223,
            0.2029580145696681,
            0.9690286675623457,
        )
        assert abs(mom_op.drift.gamma - 1.491037242289643) < 1e-10

    def test_moving_window(self):
        """test that the user may set moving window"""
        grid = picmi.Cartesian3DGrid(
            number_of_cells=[192, 2048, 12],
            lower_bound=[0, 0, 0],
            upper_bound=[3.40992e-5, 9.07264e-5, 2.1312e-6],
            lower_boundary_conditions=["open", "open", "periodic"],
            upper_boundary_conditions=["open", "open", "periodic"],
        )
        solver = picmi.ElectromagneticSolver(method="Yee", grid=grid)
        sim = picmi.Simulation(
            time_step_size=1.39e-16, max_steps=int(2048), solver=solver, picongpu_moving_window_move_point=0.9
        )
        pypic = sim.get_as_pypicongpu()

        assert abs(pypic.moving_window.move_point - 0.9) < 1e-10
        assert pypic.moving_window.stop_iteration is None

    def test_add_ionization_model(self):
        """ionization model is added correctly"""
        e = picmi.Species(name="e", particle_type="electron")
        ion1 = picmi.Species(name="hydrogen", particle_type="H", charge_state=+1)
        ion2 = picmi.Species(name="nitrogen", particle_type="N", charge_state=+2)

        ionization_model_1 = ADK(
            ADK_variant=ADKVariant.LinearPolarization,
            ionization_current=None,
            ion_species=ion1,
            ionization_electron_species=e,
        )
        ionization_model_2 = ADK(
            ADK_variant=ADKVariant.LinearPolarization,
            ionization_current=None,
            ion_species=ion2,
            ionization_electron_species=e,
        )
        interaction = [ionization_model_1, ionization_model_2]

        sim = self.sim
        sim.add_species(e, None)
        sim.add_species(ion1, None)
        sim.add_species(ion2, None)

        # in use should be set via simulation constructor
        sim.picongpu_interaction = interaction

        pypic_sim = sim.get_as_pypicongpu()
        operations = pypic_sim.init_operations

        # Every SetChargeState op must carry the charge state that was requested for its
        # species, and every species with a requested charge state must be matched by
        # exactly one op. Name-keyed lookup is deliberately avoided here: a rename or a
        # value mismatch must fail the assertions instead of silently bypassing them.
        set_charge_state_ops = [op for op in operations if isinstance(op, species.operation.SetChargeState)]
        expected_charge_states = {ion.name: ion.charge_state for ion in (ion1, ion2)}
        assert len(set_charge_state_ops) == len(expected_charge_states)
        for op in set_charge_state_ops:
            assert op.species.name in expected_charge_states, f"no charge state requested for {op.species.name=}"
            assert op.charge_state == expected_charge_states.pop(op.species.name)
        assert not expected_charge_states, f"missing SetChargeState op for {expected_charge_states}"

    def test_write_input_file(self):
        """sanity check picmi upstream: write input file"""
        sim = self.sim
        outdir = self.__get_tmpdir_name()
        assert not os.path.isdir(outdir)
        sim.write_input_file(outdir)
        assert os.path.isdir(outdir)
        assert os.path.exists(outdir + "/include/picongpu/param/simulation.param")

    def test_write_input_file_regenerates_existing_setup(self):
        """regenerating input into an already generated setup dir overwrites the old files (#5752)"""
        sim = self.sim
        outdir = self.__get_tmpdir_name()
        sim.write_input_file(outdir)

        # a rendered file from a nested template dir, rendered by the runner itself
        nested_file = outdir + "/etc/picongpu/N.cfg"
        assert os.path.exists(nested_file)
        with open(nested_file) as file:
            nested_content = file.read()
        # a param rendered from a default template
        param_file = outdir + "/include/picongpu/param/simulation.param"
        assert os.path.exists(param_file)
        with open(param_file) as file:
            param_content = file.read()

        # simulate stale/modified output from the previous generation
        for file in (nested_file, param_file):
            with open(file, "w") as f:
                f.write("stale")

        sim.write_input_file(outdir, exist_ok=True)

        with open(nested_file) as file:
            assert file.read() == nested_content
        with open(param_file) as file:
            assert file.read() == param_content

    def test_custom_template_dir_basic_write_input_file(self):
        """providing custom template dir possible or write_input_file"""
        # note: automatically cleaned up in teardown
        out_dir = self.__get_tmpdir_name()

        with tempfile.TemporaryDirectory() as tmpdir:
            # create test template dir
            # -> use include/picongpu,
            #    because pic-create does not copy every dir
            os.makedirs(tmpdir + "/include/picongpu")
            with open(tmpdir + "/include/picongpu/time_steps.mustache", "w") as testfile:
                testfile.write("{{{time_steps}}}")

            grid = get_grid(1, 1, 1, 32)
            solver = picmi.ElectromagneticSolver(method="Yee", grid=grid)
            # explicitly set to None
            sim = picmi.Simulation(
                time_step_size=17,
                max_steps=128,
                solver=solver,
                picongpu_template_dir=tmpdir,
            )
            sim.write_input_file(out_dir)

        # check for generated (rendered) dir
        assert os.path.isfile(out_dir + "/include/picongpu/time_steps")
        with open(out_dir + "/include/picongpu/time_steps") as rendered_file:
            assert rendered_file.read() == "128"

        # JSON has been dumped
        assert os.path.isfile(out_dir + "/metadata/pypicongpu_rendering_context.json")
        assert os.path.isfile(out_dir + "/metadata/pypicongpu_runner.json")
        assert os.path.isfile(out_dir + "/metadata/rc_params.json")

    def test_custom_input_basic_write_input_file(self):
        """test custom input may be rendered"""
        # note: automatically cleaned up in teardown
        out_dir = self.__get_tmpdir_name()

        # create bare bone PICMI-simulation
        grid = get_grid(1, 1, 1, 32)
        solver = picmi.ElectromagneticSolver(method="Yee", grid=grid)
        sim = picmi.Simulation(
            time_step_size=17,
            max_steps=128,
            solver=solver,
        )

        # add custom input
        i_1 = customuserinput.CustomUserInput()
        i_2 = customuserinput.CustomUserInput()

        i_1.addToCustomInput({"test_data_1": 1}, "tag_1")
        i_2.addToCustomInput({"test_data_2": 2}, "tag_2")

        sim.picongpu_add_custom_user_input(i_1)
        sim.picongpu_add_custom_user_input(i_2)

        # write simulation
        sim.write_input_file(out_dir)

        # check for generated (rendered) dir
        assert os.path.isdir(out_dir)

        # JSON has been dumped
        assert os.path.isfile(out_dir + "/metadata/pypicongpu_rendering_context.json")
        assert os.path.isfile(out_dir + "/metadata/pypicongpu_runner.json")
        assert os.path.isfile(out_dir + "/metadata/rc_params.json")

    def test_custom_template_dir_basic_get_runner(self):
        """using picongpu_get_runner() directly sets template dir"""
        with tempfile.TemporaryDirectory() as tmpdir:
            grid = get_grid(1, 1, 1, 32)
            solver = picmi.ElectromagneticSolver(method="Yee", grid=grid)
            # explicitly set to None
            sim = picmi.Simulation(
                time_step_size=17,
                max_steps=128,
                solver=solver,
                picongpu_template_dir=tmpdir,
            )
            runner = sim.picongpu_get_runner()

            assert list(map(Path.absolute, runner.template_dir)) == [Path(tmpdir).absolute()]

    def test_custom_template_dir_optional(self):
        """custom template dir is optional"""
        grid = get_grid(1, 1, 1, 32)
        solver = picmi.ElectromagneticSolver(method="Yee", grid=grid)
        # explicitly set to None
        sim = picmi.Simulation(time_step_size=17, max_steps=4, solver=solver, picongpu_template_dir=None)

        # simulation is valid
        assert self.sim.get_as_pypicongpu().get_rendering_context() != {}
        runner = sim.picongpu_get_runner()

        # good default template dir is selected
        assert runner.template_dir is not None
        assert runner.template_dir != ""

    def test_custom_template_dir_checks(self):
        """sanity checks are run on template dir"""
        grid = get_grid(1, 1, 1, 32)
        solver = picmi.ElectromagneticSolver(method="Yee", grid=grid)

        # existing dir is ok:
        with tempfile.TemporaryDirectory() as tmpdir:
            template_dir_name = tmpdir
            sim = picmi.Simulation(
                time_step_size=17,
                max_steps=4,
                solver=solver,
                picongpu_template_dir=template_dir_name,
            )

            assert sim.get_as_pypicongpu().get_rendering_context() != {}
            # no throw:
            sim.picongpu_get_runner()

        # left "with" block -- tmpdir is now deleted
        # -> now raises
        with pytest.raises(Exception, match=".*template.*"):
            picmi.Simulation(
                time_step_size=17,
                max_steps=4,
                solver=solver,
                picongpu_template_dir=template_dir_name,
            )

    def test_custom_template_dir_types(self):
        """custom template dir is typechecked"""
        grid = get_grid(1, 1, 1, 32)
        solver = picmi.ElectromagneticSolver(method="Yee", grid=grid)

        valid_paths = [None, "/", Path("/")]
        for valid_path in valid_paths:
            sim = picmi.Simulation(
                time_step_size=17,
                max_steps=4,
                solver=solver,
                picongpu_template_dir=valid_path,
            )
            assert sim.get_as_pypicongpu().get_rendering_context() != {}
            # no throw:
            sim.picongpu_get_runner()

        invalid_paths = [1, 42.0]
        for invalid_path in invalid_paths:
            with pytest.raises((ValidationError, ValueError)):
                picmi.Simulation(
                    time_step_size=17,
                    max_steps=4,
                    solver=solver,
                    picongpu_template_dir=invalid_path,
                )

    def test_custom_input_pass_thru(self):
        i = customuserinput.CustomUserInput()

        i.addToCustomInput(self.customData_1[0], self.customData_1[1])
        i.addToCustomInput(self.customData_2[0], self.customData_2[1])

        self.sim.picongpu_add_custom_user_input(i)

        renderingContextGoodResult = {"test_data_1": 1, "test_data_2": 2, "tags": ["tag_1", "tag_2"]}
        assert renderingContextGoodResult == self.sim.get_as_pypicongpu().get_rendering_context()["customuserinput"]

    def test_combination_of_several_custom_inputs(self):
        i_1 = customuserinput.CustomUserInput()
        i_2 = customuserinput.CustomUserInput()

        i_1.addToCustomInput(self.customData_1[0], self.customData_1[1])
        i_2.addToCustomInput(self.customData_2[0], self.customData_2[1])

        self.sim.picongpu_add_custom_user_input(i_1)
        self.sim.picongpu_add_custom_user_input(i_2)

        renderingContextGoodResult = {"test_data_1": 1, "test_data_2": 2, "tags": ["tag_1", "tag_2"]}
        assert renderingContextGoodResult == self.sim.get_as_pypicongpu().get_rendering_context()["customuserinput"]

    def test_duplicated_tag_over_different_custom_inputs(self):
        i_1 = customuserinput.CustomUserInput()
        i_2 = customuserinput.CustomUserInput()

        i_1.addToCustomInput(self.customData_1[0], self.customData_1[1])
        i_2.addToCustomInput(self.customData_2[0], self.customData_1[1])

        self.sim.picongpu_add_custom_user_input(i_1)
        self.sim.picongpu_add_custom_user_input(i_2)

        with pytest.raises(ValueError):
            self.sim.get_as_pypicongpu().get_rendering_context()

    def test_duplicated_key_over_different_custom_inputs(self):
        i = customuserinput.CustomUserInput()
        i_sameValue = customuserinput.CustomUserInput()
        i_differentValue = customuserinput.CustomUserInput()

        duplicateKeyData_differentValue = {"test_data_1": 3}
        duplicateKeyData_sameValue = {"test_data_1": 1}

        i.addToCustomInput(self.customData_1[0], self.customData_1[1])
        i_sameValue.addToCustomInput(duplicateKeyData_sameValue, "tag_2")
        i_differentValue.addToCustomInput(duplicateKeyData_differentValue, "tag_3")

        self.sim.picongpu_add_custom_user_input(i)

        # should work
        self.sim.picongpu_add_custom_user_input(i_sameValue)
        self.sim.get_as_pypicongpu().get_rendering_context()

        with pytest.raises(ValueError, match="Key test_data_1 exist already, and specified values differ."):
            self.sim.picongpu_add_custom_user_input(i_differentValue)
            self.sim.get_as_pypicongpu().get_rendering_context()
