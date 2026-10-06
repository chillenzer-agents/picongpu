"""
This file is part of PIConGPU.
Copyright 2025 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+

Quick tests for per-species particle boundary conditions (issue #87).

Covers:
- the standard grid particle-boundary fields are accepted and unset values
  inherit the field BCs;
- the species-level ``picongpu_particle_boundary`` override (grid-as-default,
  species-as-override);
- the C++ constraint violations raised at translation time (reflecting/thermal
  on a non-absorbing-field axis; periodic with a nonzero offset);
- the per-species command-line options emitted by the N.cfg template.
"""

from unittest import TestCase

import pytest
from pydantic import ValidationError

from picongpu import picmi, templates
from picongpu.picmi.particle_boundary import ParticleBoundary
from picongpu.pypicongpu.rendering import Renderer
from picongpu.pypicongpu.species.species import Species as PyPIConGPUSpecies
from picongpu.pypicongpu.species.species_boundary import SpeciesParticleBoundary

_GRID_KWARGS = dict(
    number_of_cells=[192, 2048, 12],
    lower_bound=[0.0, 0.0, 0.0],
    upper_bound=[3.40992e-5, 9.07264e-5, 2.1312e-6],
    # field BCs: x, y open (absorbing), z periodic
    lower_boundary_conditions=["open", "open", "periodic"],
    upper_boundary_conditions=["open", "open", "periodic"],
)


def _grid(**kwargs):
    return picmi.Cartesian3DGrid(**_GRID_KWARGS, **kwargs)


class TestGridParticleBoundaryFields(TestCase):
    def test_unset_inherits_field_bcs(self):
        # Unset particle BCs inherit the field BCs (open/open/periodic).
        grid = _grid()
        assert grid.picongpu_particle_boundary_conditions == ("open", "open", "periodic")
        # ... and they translate (map open -> absorbing) without error.
        grid.get_as_pypicongpu()

    def test_vector_form_accepted(self):
        grid = _grid(
            lower_boundary_conditions_particles=["absorbing", "reflect", "periodic"],
            upper_boundary_conditions_particles=["absorbing", "reflect", "periodic"],
        )
        assert grid.picongpu_particle_boundary_conditions == ("absorbing", "reflect", "periodic")
        grid.get_as_pypicongpu()

    def test_per_axis_form_accepted(self):
        grid = _grid(
            bc_xmin_particles="absorbing",
            bc_ymin_particles="reflect",
            bc_zmin_particles="periodic",
            bc_xmax_particles="absorbing",
            bc_ymax_particles="reflect",
            bc_zmax_particles="periodic",
        )
        assert grid.picongpu_particle_boundary_conditions == ("absorbing", "reflect", "periodic")
        grid.get_as_pypicongpu()

    def test_is_computed_field_in_model_dump(self):
        # picongpu_particle_boundary_conditions is a pydantic computed_field, so
        # it must show up in model_dump().
        grid = _grid()
        dumped = grid.model_dump()
        assert tuple(dumped["picongpu_particle_boundary_conditions"]) == ("open", "open", "periodic")

    def test_lower_upper_must_agree_per_axis(self):
        # The particle-BC consistency check is a model validator, so it runs at
        # construction time.
        with pytest.raises(ValueError, match="lower and upper particle boundary conditions must be equal"):
            _grid(
                lower_boundary_conditions_particles=["absorbing", "reflect", "periodic"],
                upper_boundary_conditions_particles=["thermal", "reflect", "periodic"],
            )


class _SimBuilder:
    """Builds a minimal, translatable simulation around the shared grid."""

    def __init__(self):
        self.grid = _grid()
        solver = picmi.ElectromagneticSolver(method="Yee", grid=self.grid)
        self.sim = picmi.Simulation(time_step_size=1e-6, max_steps=4, solver=solver)

    def add_species(self, species):
        self.sim.add_species(species=species, layout=None)
        return self


def _sim_with(species_kwargs_list):
    builder = _SimBuilder()
    for kwargs in species_kwargs_list:
        builder.add_species(picmi.Species(**kwargs))
    return builder


class TestSpeciesOverride(TestCase):
    def test_species_without_override_uses_grid_default(self):
        builder = _sim_with([{"name": "electron", "particle_type": "electron"}])
        converted = builder.sim.get_as_pypicongpu().species[0]
        # grid particle BC: open/open/periodic -> absorbing absorbing periodic
        assert converted.particle_boundary.boundary == "absorbing absorbing periodic"
        assert converted.particle_boundary.offset is None
        assert converted.particle_boundary.temperature is None

    def test_species_override_applies_per_axis(self):
        builder = _sim_with(
            [
                {"name": "electron", "particle_type": "electron"},
                {
                    "name": "ion",
                    "particle_type": "H",
                    "picongpu_particle_boundary": ParticleBoundary(
                        boundary=("reflect", "absorbing", "periodic"),
                        boundary_temperature=3.0,
                    ),
                },
            ]
        )
        electron, ion = builder.sim.get_as_pypicongpu().species
        # electron: grid default
        assert electron.particle_boundary.boundary == "absorbing absorbing periodic"
        # ion: override on x -> reflecting; temperature applied on all axes
        assert ion.particle_boundary.boundary == "reflecting absorbing periodic"
        assert ion.particle_boundary.temperature == "3 3 3"

    def test_grid_override_reflect_and_thermal_on_open_axes(self):
        # reflect on x and thermal on y are both allowed because x, y fields are open.
        grid = _grid(
            lower_boundary_conditions_particles=["reflect", "thermal", "periodic"],
            upper_boundary_conditions_particles=["reflect", "thermal", "periodic"],
        )
        assert grid.picongpu_particle_boundary_conditions == ("reflect", "thermal", "periodic")
        grid.get_as_pypicongpu()


class TestConstraintViolations(TestCase):
    def test_reflecting_on_periodic_field_axis_raises(self):
        builder = _sim_with(
            [
                {
                    "name": "electron",
                    "particle_type": "electron",
                    # z field is periodic -> reflecting not allowed on z
                    "picongpu_particle_boundary": ParticleBoundary(boundary=("periodic", "periodic", "reflect")),
                }
            ]
        )
        with pytest.raises(ValueError, match="not compatible"):
            builder.sim.get_as_pypicongpu()

    def test_thermal_on_periodic_field_axis_raises(self):
        builder = _sim_with(
            [
                {
                    "name": "electron",
                    "particle_type": "electron",
                    "picongpu_particle_boundary": ParticleBoundary(boundary=("periodic", "periodic", "thermal")),
                }
            ]
        )
        with pytest.raises(ValueError, match="not compatible"):
            builder.sim.get_as_pypicongpu()

    def test_periodic_on_absorbing_field_axis_raises(self):
        builder = _sim_with(
            [
                {
                    "name": "electron",
                    "particle_type": "electron",
                    # x field is open -> periodic not allowed on x
                    "picongpu_particle_boundary": ParticleBoundary(boundary=("periodic", "absorbing", "periodic")),
                }
            ]
        )
        with pytest.raises(ValueError, match="not compatible"):
            builder.sim.get_as_pypicongpu()

    def test_periodic_with_nonzero_offset_raises(self):
        builder = _sim_with(
            [
                {
                    "name": "electron",
                    "particle_type": "electron",
                    # z is periodic-field/periodic-particle (compatible), but offset != 0
                    "picongpu_particle_boundary": ParticleBoundary(
                        boundary=("absorbing", "absorbing", "periodic"),
                        boundary_offset=(0, 0, 5),
                    ),
                }
            ]
        )
        with pytest.raises(ValueError, match="requires a 0 offset"):
            builder.sim.get_as_pypicongpu()


class TestPypicongpuBoundaryRequired(TestCase):
    def test_pypicongpu_species_requires_particle_boundary(self):
        # At the pypicongpu level the resolved particle boundary is mandatory
        # (nothing may be left to a default); the PICMI layer always supplies it.
        kwargs = dict(
            name="e",
            constants=[],
            attributes=[],
        )
        with pytest.raises(ValidationError, match="particle_boundary"):
            PyPIConGPUSpecies(**kwargs)
        # Providing it explicitly is accepted.
        sp = PyPIConGPUSpecies(
            **kwargs, particle_boundary=SpeciesParticleBoundary(boundary="absorbing absorbing periodic")
        )
        assert sp.particle_boundary.boundary == "absorbing absorbing periodic"


class TestNcfgEmission(TestCase):
    def test_emits_per_species_boundary_options(self):
        builder = _sim_with(
            [
                {"name": "electron", "particle_type": "electron"},
                {
                    "name": "ion",
                    "particle_type": "H",
                    "picongpu_particle_boundary": ParticleBoundary(
                        boundary=("reflect", "absorbing", "periodic"),
                        boundary_offset=(5, 0, 0),
                        boundary_temperature=20.0,
                    ),
                },
            ]
        )
        context = builder.sim.get_as_pypicongpu().get_rendering_context()
        Renderer.check_rendering_context(context)
        preprocessed = Renderer.get_context_preprocessed(context)

        template_path = templates.path() / "etc" / "picongpu" / "N.cfg.mustache"
        rendered = Renderer.get_rendered_template(preprocessed, template_path.read_text())
        assert "--electron_boundary absorbing absorbing periodic" in rendered
        assert "--ion_boundary reflecting absorbing periodic" in rendered
        assert "--ion_boundaryOffset 5 0 0" in rendered
        assert "--ion_boundaryTemperature 20 20 20" in rendered
        # electron kept all defaults -> no offset/temperature lines for it
        assert "--electron_boundaryOffset" not in rendered
        assert "--electron_boundaryTemperature" not in rendered
