"""Tests for rendering built-in openPMD derived fields."""

from picongpu import templates
from picongpu.picmi.grid import Cartesian3DGrid
from picongpu.pypicongpu.memory import MemoryConfig
from picongpu.pypicongpu.output.openpmd_plugin import (
    BuiltinFieldSolver,
    FieldDump,
    OpenPMDConfig,
    OpenPMDPlugin,
)
from picongpu.pypicongpu.output.timestepspec import TimeStepSpec
from picongpu.pypicongpu.particle_functor import ParticleFunctor
from picongpu.pypicongpu.rendering import Renderer
from picongpu.pypicongpu.simulation import Simulation


def test_builtin_solver_rendering_has_no_functor_struct():
    field = FieldDump(
        name="electrons_all_weightedVelocity/x",
        species="species_electrons",
        filtername=None,
        builtin_solver=BuiltinFieldSolver(
            type="deriveField::derivedAttributes::WeightedVelocity<0>",
            typename="Native_WeightedVelocity_0",
        ),
    )
    template = (templates.path() / "include/picongpu/param/fileOutput.param.mustache").read_text()
    context = {
        "derived_field_functors": [],
        "field_tmp_solvers": [field.get_solver().model_dump(mode="json")],
    }

    rendered = Renderer.get_rendered_template(Renderer.get_context_preprocessed(context), template)

    assert "struct Native_WeightedVelocity_0" not in rendered
    assert "Native_WeightedVelocity_0_species_electrons_All_Seq" not in rendered
    assert "deriveField::derivedAttributes::WeightedVelocity<0>" in rendered
    assert "species_electrons" in rendered
    assert "deriveField::CreateFieldTmpOperation_t<" in rendered
    assert "FieldTmpSolverConfig<" in rendered
    assert "pmacc::mp_transform<ValidateFieldTmpSolver_t, FieldTmpSolverConfigs>" in rendered
    assert "CreateEligible_t" not in rendered
    # The species-specific solver list must not select solvers via VectorAllSpecies;
    # FileOutputParticles (unrelated) may still legitimately use it.
    solver_section = rendered.split("using FieldTmpSolvers =", maxsplit=1)[0]
    assert "VectorAllSpecies" not in solver_section
    assert "static_assert" in rendered


def test_solver_deduplication_includes_species_and_filter(tmp_path):
    solver = BuiltinFieldSolver(type="deriveField::derivedAttributes::Density", typename="Native_Density")
    period = TimeStepSpec(specs=[{"start": 0, "stop": 10, "step": 1}])
    plugin = OpenPMDPlugin(
        sources=[
            (
                period,
                FieldDump(
                    name="electrons_all_density",
                    species="species_electrons",
                    filtername=None,
                    builtin_solver=solver,
                ),
            ),
            (
                period,
                FieldDump(
                    name="electrons_all_density_duplicate",
                    species="species_electrons",
                    filtername=None,
                    builtin_solver=solver,
                ),
            ),
            (
                period,
                FieldDump(
                    name="ions_all_density",
                    species="species_ions",
                    filtername=None,
                    builtin_solver=solver,
                ),
            ),
            (
                period,
                FieldDump(
                    name="electrons_filtered_density",
                    species="species_electrons",
                    filtername="EnergyFilter",
                    builtin_solver=solver,
                ),
            ),
        ],
        config=OpenPMDConfig(file="simData"),
    )
    plugin.setup_dir = tmp_path
    (tmp_path / "etc").mkdir()

    simulation = Simulation.model_construct(output=[plugin])
    solvers = simulation.field_tmp_solvers

    assert len(solvers) == 3
    assert {entry.species for entry in solvers} == {"species_electrons", "species_ions"}
    assert {entry.filtername for entry in solvers} == {None, "EnergyFilter"}

    serialized_plugin = plugin.model_dump(mode="json")
    assert len(serialized_plugin["sources"]) == 4
    assert serialized_plugin["sources"][0]["source"]["name"] == "electrons_all_density"


def test_custom_functor_definition_is_reused_by_species_specific_solvers():
    functor = ParticleFunctor(
        name="custom_density",
        functor_expression="1.0",
        functor_preamble=[],
        return_type=float,
    )
    period = TimeStepSpec(specs=[{"start": 0, "stop": 10, "step": 1}])
    plugins = [
        OpenPMDPlugin(
            sources=[
                (
                    period,
                    FieldDump(
                        name=f"{species}_all_custom_density",
                        species=f"species_{species}",
                        filtername=None,
                        functor=functor,
                    ),
                )
            ]
        )
        for species in ("electrons", "ions")
    ]
    simulation = Simulation.model_construct(output=plugins)

    assert len(simulation.derived_field_functors) == 1
    assert len(simulation.field_tmp_solvers) == 2
    assert simulation.field_tmp_solvers[0].attribute_type == simulation.field_tmp_solvers[1].attribute_type


def _simulation_with_builtin_solver(solver):
    period = TimeStepSpec(specs=[{"start": 0, "stop": 10, "step": 1}])
    plugin = OpenPMDPlugin(
        sources=[
            (
                period,
                FieldDump(
                    name="field",
                    species="species_electrons",
                    filtername=None,
                    builtin_solver=solver,
                ),
            )
        ]
    )
    return Simulation.model_construct(output=[plugin])


def test_plain_derived_field_keeps_one_field_tmp_slot():
    solver = BuiltinFieldSolver(type="deriveField::derivedAttributes::Density", typename="Native_Density")
    assert _simulation_with_builtin_solver(solver).field_tmp_num_slots == 1


def test_combined_attribute_requests_an_extra_field_tmp_slot():
    # CombinedDeriveSolver computes through one intermediate FieldTmp; PIConGPU
    # static_asserts fieldTmpNumSlots >= 1 + RequiredExtraSlots.
    solver = BuiltinFieldSolver(
        type=("deriveField::combinedAttributes::AverageAttribute<deriveField::derivedAttributes::WeightedVelocity<0>>"),
        typename="Average_WeightedVelocity_0",
    )
    assert _simulation_with_builtin_solver(solver).field_tmp_num_slots == 2


def test_memory_param_renders_the_computed_field_tmp_slots():
    grid = Cartesian3DGrid(
        number_of_cells=[8, 8, 8],
        lower_bound=[0, 0, 0],
        upper_bound=[1e-6, 1e-6, 1e-6],
        lower_boundary_conditions=["periodic", "periodic", "periodic"],
        upper_boundary_conditions=["periodic", "periodic", "periodic"],
    )
    context = {
        "field_tmp_num_slots": 2,
        "grid": grid.get_as_pypicongpu().model_dump(mode="json"),
        "memory_config": MemoryConfig().model_dump(mode="json"),
    }
    template = (templates.path() / "include/picongpu/param/memory.param.mustache").read_text()
    rendered = Renderer.get_rendered_template(Renderer.get_context_preprocessed(context), template)

    assert "constexpr uint32_t fieldTmpNumSlots = 2;" in rendered
