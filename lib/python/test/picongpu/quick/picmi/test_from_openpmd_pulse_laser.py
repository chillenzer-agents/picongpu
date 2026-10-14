"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+

Quick tests for FromOpenPMDPulseLaser entry-face handling (#209, task A3):
the from-openPMD laser derives its Huygens faces from ``propagation_direction``
exactly like the standard lasers (via ``BaseLaser``), and the
``on_XMin...on_ZMax`` template branch of the from-openPMD profile renders it
on those faces instead of the old hardcoded YMin.
"""

import os
import re
import tempfile

import pytest
from pydantic import ValidationError

from picongpu import picmi
from picongpu.picmi import Cartesian2DGrid, Cartesian3DGrid, ElectromagneticSolver, Simulation
from picongpu.picmi.lasers.base_laser import BaseLaser
from picongpu.picmi.lasers.from_openpmd_pulse_laser import FromOpenPMDPulseLaser

_OPENPMD_COMMON = dict(
    propagation_direction=[0.0, 1.0, 0.0],
    polarization_direction=[1.0, 0.0, 0.0],
    time_offset_si=1.0e-12,
    file_path="pulse%T.bp5",
    iteration=0,
    dataset_name="E",
    datatype="double",
    polarisationAxisOpenPMD="x",
    propagationAxisOpenPMD="y",
)


def _openpmd(**overrides) -> FromOpenPMDPulseLaser:
    return FromOpenPMDPulseLaser(**(_OPENPMD_COMMON | overrides))


def _grid(kind: int = 3) -> object:
    if kind == 2:
        return picmi.Cartesian2DGrid(
            number_of_cells=[128, 512],
            lower_bound=[0, 0],
            upper_bound=[17, 192],
            lower_boundary_conditions=["periodic", "periodic"],
            upper_boundary_conditions=["periodic", "periodic"],
        )
    return Cartesian3DGrid(
        number_of_cells=[128, 512, 256],
        lower_bound=[0, 0, 0],
        upper_bound=[17, 192, 42],
        lower_boundary_conditions=["periodic"] * 3,
        upper_boundary_conditions=["periodic"] * 3,
    )


def _rendered_incident_field(laser) -> str:
    """Render a single-laser simulation and return the incidentField.param text."""
    sim = Simulation(time_step_size=1, max_steps=2, solver=ElectromagneticSolver(method="Yee", grid=_grid()))
    sim.add_laser(laser, None)
    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = os.path.join(tmpdir, "input")
        sim.write_input_file(output_dir)
        rendered_path = os.path.join(output_dir, "include", "picongpu", "param", "incidentField.param")
        with open(rendered_path) as rendered_file:
            return rendered_file.read()


def _enabled_faces(rendered: str) -> list[str]:
    """Return the list of the six faces whose MakeSeq carries a LaserProfile."""
    faces = []
    for face in ["XMin", "XMax", "YMin", "YMax", "ZMin", "ZMax"]:
        if re.search(r"using %s = MakeSeq_t<[^>]*LaserProfile" % face, rendered, re.DOTALL):
            faces.append(face)
    return faces


def test_from_openpmd_uses_the_standard_entry_faces_machinery():
    """`entry_faces` and `on_*` come from BaseLaser, as for the other lasers (#209,
    A3: previously the from-openPMD profile was hardcoded to YMin in the template
    and ``picongpu_entry_faces`` effectively did nothing for it)."""
    laser = _openpmd()
    assert isinstance(laser, BaseLaser)
    assert laser.picongpu_entry_faces is None
    assert laser.entry_faces == ["YMin"]
    translated = laser.get_as_pypicongpu()
    assert translated.entry_faces == ["YMin"]
    assert translated.on_YMin
    assert not (
        translated.on_XMin or translated.on_XMax or translated.on_YMax or translated.on_ZMin or translated.on_ZMax
    )

    # an explicit face list equal to the derived one is accepted and honored
    override = _openpmd(picongpu_entry_faces=["YMin"])
    assert override.entry_faces == ["YMin"]
    assert override.get_as_pypicongpu().on_YMin
    rendered = _rendered_incident_field(override)
    assert _enabled_faces(rendered) == ["YMin"]


def test_from_openpmd_derives_faces_from_direction():
    """All axis-parallel directions give the same face as entry_faces_from_direction
    would (the direction determines the crossed face, the record axis letter does
    not; see test_from_openpmd_record_axis_may_differ_from_direction)."""
    cases = [
        ([1.0, 0.0, 0.0], [0.0, 1.0, 0.0], ["XMin"]),
        ([-1.0, 0.0, 0.0], [0.0, 1.0, 0.0], ["XMax"]),
        ([0.0, 1.0, 0.0], [1.0, 0.0, 0.0], ["YMin"]),
        ([0.0, -1.0, 0.0], [1.0, 0.0, 0.0], ["YMax"]),
        ([0.0, 0.0, 1.0], [1.0, 0.0, 0.0], ["ZMin"]),
        ([0.0, 0.0, -1.0], [1.0, 0.0, 0.0], ["ZMax"]),
    ]
    for propagation, polarization, expected_faces in cases:
        laser = _openpmd(propagation_direction=propagation, polarization_direction=polarization)
        assert laser.entry_faces == expected_faces, f"direction {propagation} -> {laser.entry_faces}"
        assert laser.get_as_pypicongpu().entry_faces == expected_faces


def test_from_openpmd_record_axis_may_differ_from_direction():
    """The record axis letter does not have to match the direction's axis (#209, A3).

    ``propagationAxisOpenPMD`` names the axis the stored record runs along; the
    core (``OpenPMDdata<T_Params>``) aligns that record axis with the
    simulation's propagation axis and rotates the stored data, so a record
    stored along x may be injected along +y. Pinning this down guards against
    regressing to an artificial frontend limitation. The face is still derived
    from the direction (here: YMin)."""
    laser = _openpmd(
        propagation_direction=[0.0, 1.0, 0.0],
        polarization_direction=[1.0, 0.0, 0.0],
        propagationAxisOpenPMD="x",
        polarisationAxisOpenPMD="z",
    )
    assert laser.entry_faces == ["YMin"]
    assert _enabled_faces(_rendered_incident_field(laser)) == ["YMin"]


def test_from_openpmd_rejects_non_axis_parallel_direction():
    """The C++ core profile requires an axis-parallel propagation direction (the
    record resolves the time delay along a single axis only; the core asserts it
    at compile time), so the frontend rejects oblique directions with a readable
    error. (#209, A3)"""
    with pytest.raises(ValidationError, match="axis-parallel"):
        _openpmd(
            propagation_direction=[0.5, 0.8660254037844386, 0.0],
            polarization_direction=[0.8660254037844386, -0.5, 0.0],
        )
    # diagonal in all three axes
    d = 1.0 / 1.7320508075688772
    with pytest.raises(ValidationError, match="axis-parallel"):
        _openpmd(
            propagation_direction=[d, d, d],
            # orthogonal to [1,1,1], unit length
            polarization_direction=[-0.7071067811865476, 0.7071067811865476, 0.0],
        )


def test_from_openpmd_rejects_non_axis_parallel_polarization():
    """The C++ core profile also requires an axis-parallel polarization direction
    (compile-time assert), mirrored in the frontend. (#209, A3)"""
    with pytest.raises(ValidationError, match="axis-parallel"):
        _openpmd(
            propagation_direction=[0.0, 1.0, 0.0],
            polarization_direction=[0.7071067811865476, 0.0, 0.7071067811865476],
        )


def test_from_openpmd_rendered_on_derived_face_not_hardcoded_ymin():
    """A +y-direction pulse still renders on YMin (regression); a +z pulse is a
    genuine behavior change (it used to render on YMin) and must now render
    on ZMin via the new on_ZMin flag. (#209, A3)"""
    rendered_y = _rendered_incident_field(_openpmd())
    assert _enabled_faces(rendered_y) == ["YMin"]

    laser = _openpmd(propagation_direction=[0.0, 0.0, 1.0], propagationAxisOpenPMD="z")
    rendered: str = _rendered_incident_field(laser)
    assert _enabled_faces(rendered) == ["ZMin"], _enabled_faces(rendered)
    # the from-openPMD profile is listed under that exact face guard:
    block = re.search(r"using ZMin = MakeSeq_t<(.*?)>;", rendered, re.DOTALL).group(1)
    assert "LaserProfile_0" in block


def test_from_openpmd_explicit_entry_faces_respected():
    """An explicit face list drives the on_* flags (proof that A3 removes the
    old hardcoded YMin behavior instead of just re-validating)."""
    # explicit ZMin on a +z pulse renders on ZMin
    explicit = _openpmd(
        propagation_direction=[0.0, 0.0, 1.0],
        propagationAxisOpenPMD="z",
        picongpu_entry_faces=["ZMin"],
    )
    assert explicit.get_as_pypicongpu().entry_faces == ["ZMin"]
    assert _enabled_faces(_rendered_incident_field(explicit)) == ["ZMin"]


def test_from_openpmd_explicit_multi_face_list_is_rendered():
    """The solver accepts any profile under any face list, so an explicit
    multi-face list is rendered under every listed face, the same machinery as
    for the standard lasers. (#209, A3) Whether the faces physically make sense
    for the given direction (here: the pulse enters through both z faces) is the
    user's responsibility, as noted in the docs."""
    both = _openpmd(
        propagation_direction=[0.0, 0.0, 1.0],
        propagationAxisOpenPMD="z",
        picongpu_entry_faces=["ZMin", "ZMax"],
    )
    assert both.get_as_pypicongpu().entry_faces == ["ZMin", "ZMax"]
    rendered = _rendered_incident_field(both)
    assert _enabled_faces(rendered) == ["ZMin", "ZMax"]
    for face in ["ZMin", "ZMax"]:
        block = re.search(rf"using {face} = MakeSeq_t<(.*?)>;", rendered, re.DOTALL).group(1)
        assert "LaserProfile_0" in block


def test_from_openpmd_2d_rejects_z_faces():
    """A 2D simulation has no z coordinate; a from-openPMD pulse that would
    enter through a Z face (derived or explicit) is rejected, the same as for
    the standard lasers (the core prunes the Z faces in 2D, EnabledProfiles.hpp).
    (#209, A3)"""
    grid = _grid(kind=2)
    solver = ElectromagneticSolver(method="Yee", grid=grid)

    # +z propagation -> ZMin in 3D; rejected in 2D
    z_laser = _openpmd(propagation_direction=[0.0, 0.0, 1.0], propagationAxisOpenPMD="z")
    sim = Simulation(time_step_size=1, max_steps=2, solver=solver)
    sim.add_laser(z_laser, None)
    with pytest.raises(Exception, match="Z face"):
        sim.get_as_pypicongpu()

    # -z propagation -> ZMax in 3D; also rejected in 2D
    zmax_laser = _openpmd(propagation_direction=[0.0, 0.0, -1.0], propagationAxisOpenPMD="z")
    sim = Simulation(time_step_size=1, max_steps=2, solver=solver)
    sim.add_laser(zmax_laser, None)
    with pytest.raises(Exception, match="Z face"):
        sim.get_as_pypicongpu()

    # an in-plane +y pulse has no derived Z face; it should still build
    y_laser = _openpmd()
    sim = Simulation(time_step_size=1, max_steps=2, solver=solver)
    sim.add_laser(y_laser, None)
    assert sim.get_as_pypicongpu() is not None


def test_from_openpmd_rendered_incident_field_output():
    """The from-openPMD branch still produces the expected C++ param (regression
    on the template change: filename is rendered as before, and in the default
    +y case exactly one face is enabled)."""
    rendered = _rendered_incident_field(_openpmd())
    assert "PyPIConGPUFromOpenPMDPulseParam_0" in rendered
    assert 'filename = "pulse%T.bp5"' in rendered
    assert "FromOpenPMDPulse<PyPIConGPUFromOpenPMDPulseParam_0>" in rendered
    assert _enabled_faces(rendered) == ["YMin"]
