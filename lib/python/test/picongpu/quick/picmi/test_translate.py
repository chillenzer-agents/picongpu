"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+

Quick tests for the pure, graphlib-based PICMI -> PyPIConGPU translation
(`picmi.translate.translate`), per issue #107.

- Test A (equality, Q2 + purity, Q3): for a representative set of well-formed
  `Simulation`s, the pure `translate` reproduces the incumbent
  `get_as_pypicongpu` under normalisation and leaves the *entire* reachable input
  graph unmutated (snapshot of every reachable object, not just species).
- Test B (upstream #5727, Q6): with the `__init__`-level registration switch off,
  an `IonizationModel` that is constructed but never added to
  `picongpu_interaction` no longer mutates the ion species; with the switch on,
  the incumbent behaviour holds. `translate`'s output is shown to be independent
  of the switch (an added model always yields ionization; an unadded one never
  does, in either switch state).
- Conflict/uniqueness semantics (Q4/`species_requirements`): a genuinely
  conflicting requirement raises `RequirementConflict`; an agreeing one is
  deduplicated, matching the incumbent path that `translate` routes through.
- Topological order: applying the re-derivation in referenced-before-referrer
  order preserves the incumbent output, while reversed order does not, so the
  graphlib sort is load-bearing.
"""

import os
import sys
from contextlib import contextmanager
from unittest import TestCase

# The end_to_end corpus is not a package under test/picongpu; make it importable
# before the PICMI imports so the cheap sim-construction builders can be reused.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import picongpu.picmi as picmi  # noqa: E402
from picongpu.picmi import mutation_switch  # noqa: E402
from picongpu.picmi.diagnostics import Checkpoint, TimeStepSpec  # noqa: E402
from picongpu.picmi.diagnostics.radiation import Radiation, RadiationObserverConfiguration  # noqa: E402
from picongpu.picmi.interaction.ionization.fieldionization.ionizationcurrent.energyconservation import (  # noqa: E402
    EnergyConservation,
)
from picongpu.picmi.species import Species as PICMI_Species  # noqa: E402
from picongpu.picmi.species_requirements import RequirementConflict  # noqa: E402
from picongpu.picmi.translate import (  # noqa: E402
    _apply_cross_object_constraints,
    _reset_cross_object_requirements,
    deep_copy,
    normalize,
    translate,
    topological_order,
    Walk,
)
from picongpu.pypicongpu.species.constant.charge import Charge  # noqa: E402

import sympy  # noqa: E402
from pydantic import BaseModel  # noqa: E402

NUMBER_OF_CELLS = [64, 64, 32]
UPPER_BOUNDARY = [64.0, 66.0, 74.0]


def _grid():
    return picmi.Cartesian3DGrid(
        number_of_cells=NUMBER_OF_CELLS,
        lower_bound=[0, 0, 0],
        upper_bound=UPPER_BOUNDARY,
        lower_boundary_conditions=["open", "open", "open"],
        upper_boundary_conditions=["open", "open", "open"],
    )


def _base_sim():
    return picmi.Simulation(
        max_steps=0,
        solver=picmi.ElectromagneticSolver(method="Yee", cfl=1.0, grid=_grid()),
    )


def _uniform():
    return picmi.UniformDistribution(density=1.0e25)


def _basic_species(name, particle_type="electron"):
    return picmi.Species(name=name, particle_type=particle_type, initial_distribution=_uniform())


# ---------------------------------------------------------------------------
# Simulations used by Test A (equality). Each builder returns a fresh,
# well-formed Simulation.
# ---------------------------------------------------------------------------


def _sim_minimal():
    return _base_sim()


def _sim_single_species():
    sim = _base_sim()
    sim.add_species(_basic_species("electron"), picmi.PseudoRandomLayout(n_macroparticles_per_cell=2))
    return sim


def _sim_distributions():
    sim = _base_sim()
    sim.add_species(_basic_species("uniform"), picmi.PseudoRandomLayout(n_macroparticles_per_cell=1))
    sim.add_species(
        picmi.Species(
            name="gaussian",
            particle_type="electron",
            initial_distribution=picmi.GaussianDistribution(
                density=1.0e25,
                center_front=29.0,
                center_rear=54.0,
                sigma_front=10.0,
                sigma_rear=3.0,
                power=2.0,
                factor=-2.0,
                vacuum_front=14.0,
            ),
        ),
        picmi.PseudoRandomLayout(n_macroparticles_per_cell=1),
    )
    sim.add_species(
        picmi.Species(
            name="foil",
            particle_type="electron",
            initial_distribution=picmi.FoilDistribution(
                density=8.0e24,
                front=10.0,
                thickness=17.0,
                exponential_pre_plasma_length=12.0,
                exponential_pre_plasma_cutoff=14.0,
                exponential_post_plasma_length=5.0,
                exponential_post_plasma_cutoff=16.0,
            ),
        ),
        picmi.PseudoRandomLayout(n_macroparticles_per_cell=1),
    )
    sim.add_species(
        picmi.Species(
            name="cylindrical",
            particle_type="electron",
            initial_distribution=picmi.CylindricalDistribution(
                density=8.0e24,
                center_position=(17.0, 23.0, 45.0),
                radius=10.0,
                cylinder_axis=(1.0, 2.0, 3.0),
                exponential_pre_plasma_length=5.0,
                exponential_pre_plasma_cutoff=3.0,
            ),
        ),
        picmi.PseudoRandomLayout(n_macroparticles_per_cell=1),
    )
    return sim


def _sim_layouts():
    sim = _base_sim()
    for name, layout in {
        "oneposition": picmi.OnePositionLayout(n_macroparticles_per_cell=2),
        "gridded": picmi.GriddedLayout(n_macroparticle_per_cell=(1, 2, 3)),
        "pseudorandom": picmi.PseudoRandomLayout(n_macroparticles_per_cell=2),
    }.items():
        sim.add_species(_basic_species(name), layout)
    return sim


def _sim_diagnostics():
    from end_to_end.test_diagnostics import SPECIES, generate_diagnostics

    sim = _base_sim()
    for species in SPECIES:
        sim.add_species(species, picmi.OnePositionLayout(n_macroparticles_per_cell=2))
    sim.diagnostics = [Checkpoint(period=TimeStepSpec[:])] + generate_diagnostics(
        sim.species,
        [
            picmi.ParticleFunctor(name="density", functor=lambda p: p.get("weighting") / 268.125),
            picmi.ParticleFunctor(name="kinetic_energy", functor=lambda p: p.get("kinetic energy")),
        ],
    )
    return sim


def _sim_ionization():
    sim = _base_sim()
    ion = picmi.Species(name="ion", particle_type="H", charge_state=1, initial_distribution=_uniform())
    electron = _basic_species("electron")
    sim.add_species(ion, picmi.PseudoRandomLayout(n_macroparticles_per_cell=1))
    sim.add_species(electron, picmi.PseudoRandomLayout(n_macroparticles_per_cell=1))
    sim.picongpu_interaction = [
        picmi.ADK(
            ADK_variant=picmi.ADKVariant.LinearPolarization,
            ion_species=ion,
            ionization_electron_species=electron,
            ionization_current=EnergyConservation(),
        )
    ]
    return sim


def _sim_synchrotron():
    sim = _base_sim()
    electron = _basic_species("electron")
    photon = picmi.Species(
        name="photon",
        particle_type="other:photon",
        mass=1.0e-30,
        charge=0.0,
        initial_distribution=_uniform(),
    )
    sim.add_species(electron, picmi.PseudoRandomLayout(n_macroparticles_per_cell=1))
    sim.add_species(photon, picmi.PseudoRandomLayout(n_macroparticles_per_cell=1))
    sim.picongpu_interaction = [picmi.Synchrotron(electron_species=electron, photon_species=photon)]
    return sim


def _sim_radiation(gamma_filter_threshold=None):
    # Exercises the third re-derivation branch (`Radiation` -> MomentumPrev1 /
    # RadiationMask). max_steps must be > 0 so the period resolves against the
    # step count.
    sim = picmi.Simulation(
        max_steps=100,
        solver=picmi.ElectromagneticSolver(method="Yee", cfl=1.0, grid=_grid()),
    )
    electron = _basic_species("electron")
    sim.add_species(electron, picmi.PseudoRandomLayout(n_macroparticles_per_cell=1))
    n_observer = 4
    radiation = Radiation(
        species=electron,
        period=TimeStepSpec[10::10],
        gamma_filter_threshold=gamma_filter_threshold,
        observer=RadiationObserverConfiguration(
            N_observer=n_observer,
            index_to_direction=lambda i: [
                sympy.sin(2 * sympy.pi / n_observer * i),
                sympy.cos(2 * sympy.pi / n_observer * i),
                0,
            ],
        ),
    )
    sim.diagnostics = [radiation]
    return sim


def _sim_radiation_masked():
    return _sim_radiation(gamma_filter_threshold=1.5)


SIM_BUILDERS = [
    ("minimal", _sim_minimal),
    ("single_species", _sim_single_species),
    ("distributions", _sim_distributions),
    ("layouts", _sim_layouts),
    ("diagnostics", _sim_diagnostics),
    ("ionization", _sim_ionization),
    ("synchrotron", _sim_synchrotron),
    ("radiation", _sim_radiation),
    ("radiation_masked", _sim_radiation_masked),
]


# ---------------------------------------------------------------------------
# Test A: equality (Q2) + purity (Q3)
# ---------------------------------------------------------------------------


def _canon(value):
    """Canonical, comparable view of an arbitrary field value.

    Nested models are captured *by identity* (a replaced object shows up as a
    changed id); sequences/dicts recurse; simple scalars compare by value; and
    anything non-trivial (numpy arrays, callables, sympy exprs) is captured by
    its repr so the comparison stays elementwise-free and side-effect-free.
    """
    if isinstance(value, BaseModel):
        return ("model", id(value))
    if isinstance(value, (list, tuple, set, frozenset)):
        return ("seq", tuple(_canon(item) for item in value))
    if isinstance(value, dict):
        return ("dict", tuple((key, _canon(item)) for key, item in sorted(value.items(), key=str)))
    if value is None or isinstance(value, (str, int, float, bool)):
        return ("scalar", value)
    return ("scalar", repr(value))


def _object_state(obj):
    """The state of a reachable PICMI object: its public and private attributes."""
    state = [(key, _canon(value)) for key, value in sorted(vars(obj).items(), key=str)]
    private = getattr(obj, "__pydantic_private__", None) or {}
    state += [(f"private:{key}", _canon(value)) for key, value in sorted(private.items(), key=str)]
    return tuple(state)


def _reachable_snapshot(root):
    """Snapshot the full reachable PICMI object graph, keyed by object id."""
    return {id(obj): _object_state(obj) for obj in Walk(root)}


class TestTranslateEquality(TestCase):
    def test_translate_matches_incumbent(self):
        """normalize(translate(sim)) == normalize(sim.get_as_pypicongpu()) for a
        representative set of well-formed Simulations (Q2)."""
        for name, builder in SIM_BUILDERS:
            with self.subTest(sim=name):
                sim = builder()
                self.assertEqual(
                    normalize(sim.get_as_pypicongpu()),
                    normalize(translate(sim)),
                    msg=f"translate() diverged from get_as_pypicongpu() for {name!r}",
                )

    def test_translate_does_not_mutate_input(self):
        """translate() leaves the *entire* reachable input graph unmutated (Q3):
        every reachable object's public and private attributes are unchanged, and
        no reachable object is added or dropped. This is checked in isolation
        (only translate is called) because the incumbent get_as_pypicongpu is
        itself impure (e.g. it sets a distribution's cell_size), so the purity
        assertion cannot share a simulation state with a get_as_pypicongpu call."""
        for name, builder in SIM_BUILDERS:
            with self.subTest(sim=name):
                sim = builder()
                snapshot_before = _reachable_snapshot(sim)
                translate(sim)
                snapshot_after = _reachable_snapshot(sim)
                self.assertEqual(
                    set(snapshot_before),
                    set(snapshot_after),
                    msg=f"translate() added/dropped reachable objects for {name!r} (Q3)",
                )
                for obj_id in snapshot_before:
                    self.assertEqual(
                        snapshot_after[obj_id],
                        snapshot_before[obj_id],
                        msg=f"translate() mutated a reachable object (id {obj_id}) for {name!r} (Q3)",
                    )


# ---------------------------------------------------------------------------
# Test B: the #5727 off-switch (Q6)
# ---------------------------------------------------------------------------

_IONIZATION_REQUIREMENT_TYPES = {
    "GroundStateIonizationConstruction",
    "SetChargeStateOperation",
    "DependsOn",
    "BoundElectrons",
    "ElementProperties",
}


def _has_ionization_requirement(species):
    return any(type(requirement).__name__ in _IONIZATION_REQUIREMENT_TYPES for requirement in species._requirements)


@contextmanager
def _init_mutation(enabled: bool):
    previous = mutation_switch.INIT_MUTATION_ENABLED
    mutation_switch.INIT_MUTATION_ENABLED = enabled
    try:
        yield
    finally:
        mutation_switch.INIT_MUTATION_ENABLED = previous


def _unadded_ionization(ion, electron):
    """An ionization model constructed on (ion, electron) but NOT added to the
    simulation's `picongpu_interaction` -- the #5727 scenario."""
    return picmi.ADK(
        ADK_variant=picmi.ADKVariant.LinearPolarization,
        ion_species=ion,
        ionization_electron_species=electron,
        ionization_current=EnergyConservation(),
    )


class TestIonizationRegistrationSwitch(TestCase):
    def _make(self, added):
        sim = _base_sim()
        ion = picmi.Species(name="ion", particle_type="H", charge_state=1, initial_distribution=_uniform())
        electron = _basic_species("electron")
        sim.add_species(ion, picmi.PseudoRandomLayout(n_macroparticles_per_cell=1))
        sim.add_species(electron, picmi.PseudoRandomLayout(n_macroparticles_per_cell=1))
        model = _unadded_ionization(ion, electron)
        if added:
            sim.picongpu_interaction = [model]
        return sim, ion, model

    def test_ionization_registration_switch(self):
        # (1) switch OFF: an unadded model must NOT have mutated the ion species,
        #     and translating it yields no ionization on the ion species.
        with self.subTest(switch="off"), _init_mutation(False):
            sim, ion, _ = self._make(added=False)
            self.assertFalse(
                _has_ionization_requirement(ion),
                msg="#5727: an unadded IonizationModel still mutated the ion species",
            )
            ion_pypicongpu = next(s for s in translate(sim).species if s.name == "ion")
            self.assertIsNone(ion_pypicongpu.constants.ground_state_ionization)

        # (2) switch ON (default incumbent behaviour): the unadded model DOES
        #     register onto the ion species -- the #5727 behaviour.
        with self.subTest(switch="on"), _init_mutation(True):
            sim, ion, _ = self._make(added=False)
            self.assertTrue(
                _has_ionization_requirement(ion),
                msg="expected the incumbent __init__-level registration to pollute the ion species",
            )

        # (3) switch OFF but the model IS added: translate() derives it from the
        #     reachable interaction (reachability-driven) and still emits ionization.
        with self.subTest(switch="off_added"), _init_mutation(False):
            sim, ion, _ = self._make(added=True)
            ion_pypicongpu = next(s for s in translate(sim).species if s.name == "ion")
            self.assertIsNotNone(ion_pypicongpu.constants.ground_state_ionization)

    def test_translate_is_switch_independent(self):
        """translate()'s output depends on reachability alone, not on
        INIT_MUTATION_ENABLED: an *added* model yields ionization with the switch
        on OR off; an *unadded* model yields none with the switch on OR off.
        (Before the reset-then-re-derive fix, switch ON polluted the reachable ion
        and translate reproduced it, so the unadded case diverged by switch state.)"""
        for added in (True, False):
            expected = "SET" if added else "None"
            with self.subTest(added=added):
                for switch in (True, False):
                    with self.subTest(switch=switch), _init_mutation(switch):
                        sim, ion, _ = self._make(added=added)
                        ion_pypicongpu = next(s for s in translate(sim).species if s.name == "ion")
                        is_set = ion_pypicongpu.constants.ground_state_ionization is not None
                        self.assertEqual(
                            "SET" if is_set else "None",
                            expected,
                            msg=f"translate() output changed with the switch (added={added}, switch={switch})",
                        )


# ---------------------------------------------------------------------------
# Conflict/uniqueness semantics are delegated to the incumbent (QA #1)
# ---------------------------------------------------------------------------


class TestConflictSemantics(TestCase):
    def test_conflicting_requirement_is_caught(self):
        """A genuinely conflicting requirement (a second, disagreeing `Charge` on
        the same species) is rejected by the incumbent `resolving_add`/
        `check_for_conflict` that `translate` routes through. The conflict is
        raised at `register_requirements` time, which is shared by both
        `get_as_pypicongpu` and `translate`."""
        sim = _base_sim()
        electron = _basic_species("electron")
        sim.add_species(electron, picmi.PseudoRandomLayout(n_macroparticles_per_cell=1))
        with self.assertRaises(RequirementConflict):
            electron.register_requirements([Charge(charge_si=9.0)])

    def test_agreeing_unique_requirement_is_deduped_not_conflicted(self):
        """The same requirement registered twice is deduplicated (uniqueness), not
        treated as a conflict -- the incumbent bag-merge semantics."""
        sim = _base_sim()
        electron = _basic_species("electron")
        sim.add_species(electron, picmi.PseudoRandomLayout(n_macroparticles_per_cell=1))
        existing = next(req for req in electron._requirements if isinstance(req, Charge))
        before = len(electron._requirements)
        electron.register_requirements([Charge(charge_si=existing.charge_si)])
        self.assertEqual(len(electron._requirements), before)


# ---------------------------------------------------------------------------
# The topological order is load-bearing, not cosmetic (QA #3)
# ---------------------------------------------------------------------------


def _reset_and_apply(resolved, order):
    """Reset cross-object requirements on each reachable species, then re-derive,
    in the given order (mirrors `translate` minus the graphlib sort)."""
    for obj in order:
        if isinstance(obj, PICMI_Species):
            _reset_cross_object_requirements(obj)
        _apply_cross_object_constraints(obj)


class TestTopologicalOrderLoadBearing(TestCase):
    def test_referenced_before_referrer_is_required(self):
        """Applying constraints in topological (referenced-before-referrer) order
        preserves the ionization the incumbent produces; reversing the order
        drops it, because a referrer's re-derivation must run after its
        referenced species has been reset. This is what makes the graphlib sort
        load-bearing rather than decorative."""
        with _init_mutation(False):
            sim, ion, _ = TestIonizationRegistrationSwitch()._make(added=True)
            ref = normalize(translate(sim))

            ctx = {}
            resolved = deep_copy(sim, ctx)
            _reset_and_apply(resolved, topological_order(resolved))
            self.assertEqual(normalize(resolved.get_as_pypicongpu()), ref)

            ctx = {}
            resolved = deep_copy(sim, ctx)
            _reset_and_apply(resolved, list(reversed(topological_order(resolved))))
            self.assertNotEqual(
                normalize(resolved.get_as_pypicongpu()),
                ref,
                msg="reversed order unexpectedly matched -- the topo order would be cosmetic",
            )
