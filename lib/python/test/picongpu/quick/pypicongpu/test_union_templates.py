"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+

Union exhaustiveness (task 06): rendering must have a template fragment for
every allowed union member. Without this check a future union member without
a render template would only fail at render/compile time. Each mapping entry
pins the mustache anchor the renderer keys off on for that member.
"""

from pathlib import Path
from typing import get_args

import pytest

import picongpu.templates
from picongpu.pypicongpu.field_solver import AnySolver, LeheSolver, YeeSolver
from picongpu.pypicongpu.laser import (
    AnyLaser,
    DispersivePulseLaser,
    FromOpenPMDPulseLaser,
    GaussianLaser,
    PlaneWaveLaser,
    TWTSLaser,
)
from picongpu.pypicongpu.output import (
    AnyPlugin,
    Binning,
    Checkpoint,
    EnergyHistogram,
    MacroParticleCount,
    OpenPMDPlugin,
    PhaseSpace,
    RadiationPlugin,
)
from picongpu.pypicongpu.species.operation import AnyOperation, SetChargeState, SimpleDensity, SimpleMomentum
from picongpu.pypicongpu.species.operation.layout import AnyLayout, OnePosition, Quiet, Random

TEMPLATES = Path(picongpu.templates.path())

# union member -> (template file relative to the template root, mustache anchor)
_UNION_TEMPLATE_ANCHORS = {
    AnyLaser: {
        GaussianLaser: ("include/picongpu/param/incidentField.param.mustache", "{{#type_gaussian}}"),
        PlaneWaveLaser: ("include/picongpu/param/incidentField.param.mustache", "{{#type_planewave}}"),
        DispersivePulseLaser: ("include/picongpu/param/incidentField.param.mustache", "{{#type_dispersive}}"),
        FromOpenPMDPulseLaser: ("include/picongpu/param/incidentField.param.mustache", "{{#type_fromOpenPMDPulse}}"),
        TWTSLaser: ("include/picongpu/param/incidentField.param.mustache", "{{#type_twts}}"),
    },
    AnyPlugin: {
        Binning: ("include/picongpu/param/binningSetup.param.mustache", "{{#type_binning}}"),
        Checkpoint: ("etc/picongpu/N.cfg.mustache", "{{#type_checkpoint}}"),
        EnergyHistogram: ("etc/picongpu/N.cfg.mustache", "{{#type_energyhistogram}}"),
        MacroParticleCount: ("etc/picongpu/N.cfg.mustache", "{{#type_macroparticlecount}}"),
        OpenPMDPlugin: ("include/picongpu/param/fileOutput.param.mustache", "{{#type_openPMD}}"),
        PhaseSpace: ("etc/picongpu/N.cfg.mustache", "{{#type_phasespace}}"),
        RadiationPlugin: ("include/picongpu/param/radiation.param.mustache", "{{#type_radiation}}"),
    },
    # both solvers are rendered through the generic {{{solver.name}}} slot
    AnySolver: {
        YeeSolver: ("include/picongpu/param/fieldSolver.param.mustache", "{{{solver.name}}}"),
        LeheSolver: ("include/picongpu/param/fieldSolver.param.mustache", "{{{solver.name}}}"),
    },
    AnyLayout: {
        Random: ("include/picongpu/param/particle.param.mustache", "{{#layout.type_random}}"),
        Quiet: ("include/picongpu/param/particle.param.mustache", "{{#layout.type_quiet}}"),
        OnePosition: ("include/picongpu/param/particle.param.mustache", "{{#layout.type_one_position}}"),
    },
    AnyOperation: {
        SimpleDensity: ("include/picongpu/param/speciesInitialization.param.mustache", "{{#type_simpledensity}}"),
        SimpleMomentum: ("include/picongpu/param/speciesInitialization.param.mustache", "{{#type_simplemomentum}}"),
        SetChargeState: ("include/picongpu/param/speciesInitialization.param.mustache", "{{#type_setchargestate}}"),
    },
}


def _union_members(union):
    return [member for member in get_args(union) if isinstance(member, type)]


def _union_id(union):
    return getattr(union, "__name__", str(union))


@pytest.mark.parametrize("union", list(_UNION_TEMPLATE_ANCHORS), ids=_union_id)
def test_union_members_all_mapped(union):
    # adding a union member without a template anchor (or leaving a stale
    # entry) must fail here, not at render time
    assert set(_union_members(union)) == set(_UNION_TEMPLATE_ANCHORS[union])


@pytest.mark.parametrize(
    ("union", "member", "template_file", "anchor"),
    [
        (union, member, template_file, anchor)
        for union, members in _UNION_TEMPLATE_ANCHORS.items()
        for member, (template_file, anchor) in members.items()
    ],
    ids=lambda value: getattr(value, "__name__", str(value)),
)
def test_union_member_has_template_fragment(union, member, template_file, anchor):
    template = (TEMPLATES / template_file).read_text()
    assert anchor in template, f"no template fragment for {member.__name__} in {template_file!r} ({anchor!r})"
