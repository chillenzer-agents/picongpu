"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: opencode
License: GPLv3+

Render regression test: the vector-shaped pieces of the generated C++ must be
byte-identical to what the previous section-based (/ component-model based)
rendering produced. Only the Python side (serialisation + templates) changed;
the emitted .param files must not.
"""

from pathlib import Path

from picongpu import picmi


def _setup(sim, outdir: Path):
    grid = picmi.Cartesian3DGrid(
        number_of_cells=[32, 32, 32],
        lower_bound=[0, 0, 0],
        upper_bound=[32e-6, 32e-6, 32e-6],
        lower_boundary_conditions=["open", "open", "periodic"],
        upper_boundary_conditions=["open", "open", "periodic"],
    )
    solver = picmi.ElectromagneticSolver(method="Yee", grid=grid)
    sim = picmi.Simulation(time_step_size=1.7e-13, max_steps=32, solver=solver)

    dist = picmi.UniformDistribution(
        density=1e24,
        rms_velocity=[2e6, 3e6, 4e6],
        directed_velocity=[1e6, 2e6, 3e6],
    )
    sim.add_species(
        picmi.Species(name="electron", mass=1, charge=-1, initial_distribution=dist),
        picmi.OnePositionLayout(n_macroparticles_per_cell=2, in_cell_offset=(0.1, 0.2, 0.3)),
    )
    dist_cyl = picmi.CylindricalDistribution(
        density=5e23,
        center_position=[1e-5, 2e-5, 3e-5],
        radius=4e-6,
        cylinder_axis=[0.0, 1.0, 0.0],
        exponential_pre_plasma_length=0.5e-6,
        exponential_pre_plasma_cutoff=1e-6,
    )
    sim.add_species(
        picmi.Species(name="proton", mass=1836, charge=1, initial_distribution=dist_cyl),
        picmi.GriddedLayout(n_macroparticles_per_cell=[2, 2, 2]),
    )
    laser = picmi.GaussianLaser(
        wavelength=1e-6,
        waist=5e-6,
        duration=30e-15,
        propagation_direction=[0, 1, 0],
        polarization_direction=[0, 0, 1],
        focal_position=[1e-5, 5e-6, 1e-5],
        centroid_position=[1e-5, -5e-6, 1e-5],
        E0=1e11,
        picongpu_laguerre_modes=[2.0, 3.0],
        picongpu_laguerre_phases=[4.0, 5.0],
        phi0=-1.5,
        picongpu_huygens_surface_positions=[[1, -1], [1, -1], [1, -1]],
    )
    sim.add_laser(laser, None)
    sim.write_input_file(str(outdir))


def test_incident_field_renders_keyed_vectors(tmp_path):
    """the laser direction vectors are rendered from the canonical {x, y, z} shape"""
    out_dir = tmp_path / "render"
    _setup(None, out_dir)
    incident_field = (out_dir / "include/picongpu/param/incidentField.param").read_text()
    assert (
        "static constexpr float_64 propagation_direction[3u] = {\n"
        "                0.0,\n"
        "                1.0,\n"
        "                0.0\n"
        "            };"
    ) in incident_field
    assert (
        "static constexpr float_64 polarisation_direction[3u] = {\n"
        "                0.0,\n"
        "                0.0,\n"
        "                1.0\n"
        "            };"
    ) in incident_field
    assert (
        "static constexpr auto laguerreModes = floatN_X<numModes+1>(\n            2.0,\n            3.0\n            );"
    ) in incident_field
    assert "component" not in incident_field


def test_cylinder_renders_keyed_vectors(tmp_path):
    """the cylinder centre/axis vectors are rendered from the canonical {x, y, z} shape"""
    out_dir = tmp_path / "render"
    _setup(None, out_dir)
    density = (out_dir / "include/picongpu/param/density.param").read_text()
    assert (
        "static constexpr float3_64  centerPosition_SI{\n"
        "                    1.0000000000000001e-5,\n"
        "                    2.0000000000000002e-5,\n"
        "                    3.0000000000000001e-5\n"
        "                };"
    ) in density
    assert (
        "static constexpr float3_X jetAxis{\n"
        "                    0.0_X,\n"
        "                    1.0_X,\n"
        "                    0.0_X\n"
        "                };"
    ) in density
    assert "component" not in density


def test_metadata_context_uses_canonical_shapes(tmp_path):
    """the stored rendering-context JSON uses {x, y, z} vectors and plain laguerre lists"""
    import json

    out_dir = tmp_path / "render"
    _setup(None, out_dir)
    metadata = json.loads((out_dir / "metadata/pypicongpu_rendering_context.json").read_text())
    laser = metadata["laser"][0]
    assert laser["propagation_direction"] == {"x": 0.0, "y": 1.0, "z": 0.0}
    assert laser["polarization_direction"] == {"x": 0.0, "y": 0.0, "z": 1.0}
    assert laser["laguerre_modes"] == [2.0, 3.0]
    # find the cylinder profile in the init operations
    profiles = [
        op["profile"] for op in metadata["init_operations"] if "profile" in op and "type_cylinder" in op["profile"]
    ]
    assert profiles and profiles[0]["center_position_si"] == {"x": 1e-05, "y": 2e-05, "z": 3e-05}
