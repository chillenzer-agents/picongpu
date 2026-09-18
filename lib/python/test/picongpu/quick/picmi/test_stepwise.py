"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: chillenzer-agents
License: GPLv3+
"""

import logging

from picongpu.picmi import Cartesian3DGrid, ElectromagneticSolver, Simulation
from picongpu.picmi.diagnostics import Checkpoint, TimeStepSpec
from picongpu.pypicongpu.runner import (
    Runner,
    chunk_config_filename,
    chunk_config_text,
)
from pytest import fixture, raises


def _grid(n=16):
    return Cartesian3DGrid(
        number_of_cells=[n] * 3,
        lower_bound=[0, 0, 0],
        upper_bound=[n] * 3,
        lower_boundary_conditions=["open", "open", "periodic"],
        upper_boundary_conditions=["open", "open", "periodic"],
    )


def _make_sim(tmp_path, max_steps=4, diagnostics=None):
    sim = Simulation(
        time_step_size=17,
        max_steps=max_steps,
        solver=ElectromagneticSolver(method="Yee", grid=_grid()),
        diagnostics=diagnostics or [],
    )
    sim.picongpu_get_runner(setup_dir=tmp_path / "setup", run_dir=tmp_path / "run")
    return sim


def _render_base_cfg(tmp_path, diagnostics=None):
    """Render the base setup into tmp_path and return the rendered N.cfg text."""
    sim = _make_sim(tmp_path, diagnostics=diagnostics)
    sim.picongpu_get_runner().generate()
    return (sim.picongpu_get_runner().setup_dir / "etc" / "picongpu" / "N.cfg").read_text()


def _stub_step_exec(monkeypatch):
    """Stub Runner.build_once/run_chunk so step() bookkeeping runs but not CWL/GPU.

    Returns a dict recording chunks (start, end, need_checkpoint), builds, and
    the run_dir used for each chunk. run_chunk still writes the real additive
    chunk config so it can be inspected.
    """
    calls = {"chunks": [], "builds": 0, "run_dirs": []}

    def fake_build_once(self, **flags):
        # mirror the real build_once: build at most once
        if self._built:
            return
        calls["builds"] += 1
        self._built = True

    def fake_run_chunk(self, start, end, *, need_checkpoint=True):
        calls["chunks"].append((int(start), int(end), bool(need_checkpoint)))
        calls["run_dirs"].append(str(self.run_dir))
        self.build_once()
        self.write_chunk_config(start, end, need_checkpoint=need_checkpoint)

    monkeypatch.setattr(Runner, "build_once", fake_build_once)
    monkeypatch.setattr(Runner, "run_chunk", fake_run_chunk)
    return calls


class TestChunkConfigContent:
    """The additive chunk config: TBG_steps=end, restart block, shared ckpt dir."""

    @fixture
    def base_cfg(self, tmp_path):
        return _render_base_cfg(tmp_path)

    def test_chunk_config_filename(self):
        assert chunk_config_filename(0, 2) == "N-step-0-2.cfg"
        assert chunk_config_filename(2, 4) == "N-step-2-4.cfg"

    def test_tbg_steps_set_to_chunk_end(self, base_cfg):
        text = chunk_config_text(base_cfg, 2, restart_step=None, auto_checkpoint=2)
        assert 'TBG_steps="2"' in text
        assert 'TBG_steps="4"' not in text  # not the base max_steps

    def test_fresh_chunk_tryrestart_no_restart_step(self, base_cfg):
        text = chunk_config_text(base_cfg, 2, restart_step=None, auto_checkpoint=2)
        assert "--checkpoint.tryRestart" in text
        assert "--checkpoint.restart.step" not in text
        assert "--checkpoint.restart.directory checkpoints" in text
        assert "--checkpoint.directory checkpoints" in text

    def test_restart_chunk_has_restart_step(self, base_cfg):
        text = chunk_config_text(base_cfg, 4, restart_step=2, auto_checkpoint=4)
        assert 'TBG_steps="4"' in text
        assert "--checkpoint.tryRestart" in text
        assert "--checkpoint.restart.step 2" in text
        assert "--checkpoint.restart.directory checkpoints" in text

    def test_auto_checkpoint_adds_period_at_end(self, base_cfg):
        assert "--checkpoint.period 2:2:1" in chunk_config_text(base_cfg, 2, restart_step=None, auto_checkpoint=2)
        assert "--checkpoint.period 4:4:1" in chunk_config_text(base_cfg, 4, restart_step=2, auto_checkpoint=4)

    def test_auto_checkpoint_off_adds_no_period(self, base_cfg):
        assert "--checkpoint.period" not in chunk_config_text(base_cfg, 2, restart_step=None, auto_checkpoint=None)

    def test_auto_checkpoint_merges_into_user_period(self, tmp_path):
        base_cfg = _render_base_cfg(
            tmp_path, diagnostics=[Checkpoint(period=TimeStepSpec[2], directory="ckpts", file="chk")]
        )
        assert "--checkpoint.period 2:2:1" in base_cfg
        # auto at end=4 merges into the user's 2:2:1 (never a 2nd --checkpoint.period)
        text = chunk_config_text(
            base_cfg, 4, checkpoint_directory="ckpts", checkpoint_file="chk", restart_step=2, auto_checkpoint=4
        )
        assert "--checkpoint.period 2:2:1,4:4:1" in text
        assert text.count("--checkpoint.period") == 1
        # reuses the user's dir/file (not duplicated)
        assert text.count("--checkpoint.directory") == 1
        assert "--checkpoint.directory ckpts" in text

    def test_user_checkpoint_covering_end_left_untouched(self, tmp_path):
        # auto off (user's checkpoint already covers end=2) -> period unchanged
        base_cfg = _render_base_cfg(
            tmp_path, diagnostics=[Checkpoint(period=TimeStepSpec[2], directory="ckpts", file="chk")]
        )
        text = chunk_config_text(
            base_cfg, 2, checkpoint_directory="ckpts", checkpoint_file="chk", restart_step=2, auto_checkpoint=None
        )
        assert "--checkpoint.period 2:2:1" in text
        assert text.count("--checkpoint.period") == 1
        assert 'TBG_steps="2"' in text
        assert "--checkpoint.restart.step 2" in text


class TestStepBookkeeping:
    """Global-step accumulation, guards, run_dir reuse, build-once."""

    @fixture
    def sim(self, tmp_path, monkeypatch):
        calls = _stub_step_exec(monkeypatch)
        return _make_sim(tmp_path), calls

    def test_accumulates_global_steps(self, sim):
        s, calls = sim
        assert s.step(nsteps=2) == (0, 2)
        assert s.step(nsteps=2) == (2, 4)
        assert s._steps_completed == 4
        assert calls["chunks"] == [(0, 2, True), (2, 4, True)]
        # binary built exactly once for the whole sim
        assert calls["builds"] == 1

    def test_run_dir_reused_across_chunks(self, sim):
        s, calls = sim
        s.step(nsteps=2)
        s.step(nsteps=2)
        assert calls["run_dirs"] == [str(s.picongpu_get_runner().run_dir)] * 2

    def test_chunk_configs_written_and_base_untouched(self, sim):
        s, calls = sim
        s.step(nsteps=2)
        s.step(nsteps=2)
        etc = s.picongpu_get_runner().setup_dir / "etc" / "picongpu"
        assert (etc / "N-step-0-2.cfg").is_file()
        assert (etc / "N-step-2-4.cfg").is_file()
        # base N.cfg untouched (its TBG_steps = max_steps)
        assert 'TBG_steps="4"' in (etc / "N.cfg").read_text()
        # each chunk config carries its own absolute stop
        assert 'TBG_steps="2"' in (etc / "N-step-0-2.cfg").read_text()
        assert 'TBG_steps="4"' in (etc / "N-step-2-4.cfg").read_text()

    def test_end_exceeds_max_steps(self, sim):
        s, _ = sim
        with raises(ValueError, match="exceeds max_steps"):
            s.step(nsteps=5)

    def test_out_of_order_rejected(self, sim):
        s, _ = sim
        # complete the full range via chunks (2+2), then a chunk that goes back
        # overlaps the completed range.
        s.step(nsteps=2)
        s.step(nsteps=2)
        with raises(ValueError, match="overlap"):
            s.step(start=0, end=2)

    def test_nsteps_negative_rejected(self, sim):
        s, _ = sim
        with raises(ValueError, match="nsteps must be >= 0"):
            s.step(nsteps=-1)

    def test_max_steps_none_rejected(self, monkeypatch):
        _stub_step_exec(monkeypatch)
        # a bare sim (no runner yet) with max_steps=None: step() must reject
        # before it needs the runner.
        s = Simulation(time_step_size=17, max_steps=None, solver=ElectromagneticSolver(method="Yee", grid=_grid()))
        with raises(ValueError, match="max_steps"):
            s.step(nsteps=1)

    def test_full_run_is_legacy_batched_run(self, tmp_path, monkeypatch):
        """A step() with nsteps == max_steps and no start/end is the legacy
        "run all" batched run (picongpu_run), not a foreground chunk -- this
        preserves the existing end-to-end tests that call step(0) with
        max_steps=0."""
        _stub_step_exec(monkeypatch)
        s = _make_sim(tmp_path)
        ran = {"full": False, "chunk": False}

        def fake_picongpu_run(self, *a, **k):
            ran["full"] = True
            self._steps_completed = self.max_steps

        def fake_run_chunk(self, start, end, *, need_checkpoint=True):
            ran["chunk"] = True

        monkeypatch.setattr(Simulation, "picongpu_run", fake_picongpu_run)
        monkeypatch.setattr(Runner, "run_chunk", fake_run_chunk)

        # nsteps == max_steps (4) and no explicit start/end -> legacy full run
        assert s.step(nsteps=4) == (0, 4)
        assert ran["full"] and not ran["chunk"]
        # and a zero-step "run all" (the existing e2e pattern: step(0), max 0)
        s0 = _make_sim(tmp_path, max_steps=0)
        ran0 = {"full": False, "chunk": False}

        def fake_picongpu_run0(self, *a, **k):
            ran0["full"] = True
            self._steps_completed = self.max_steps

        monkeypatch.setattr(Simulation, "picongpu_run", fake_picongpu_run0)
        monkeypatch.setattr(Runner, "run_chunk", fake_run_chunk)
        assert s0.step(0) == (0, 0)
        assert ran0["full"] and not ran0["chunk"]


class TestCheckpointPlan:
    """Auto-checkpoint scheduling and its silence conditions."""

    @fixture
    def sim(self, tmp_path, monkeypatch):
        calls = _stub_step_exec(monkeypatch)
        return _make_sim(tmp_path), calls

    def _chunk_cfg(self, s, start, end):
        return (s.picongpu_get_runner().setup_dir / "etc" / "picongpu" / chunk_config_filename(start, end)).read_text()

    def test_auto_checkpoint_warns(self, sim, caplog):
        s, calls = sim
        with caplog.at_level(logging.WARNING):
            s.step(nsteps=2)
        assert "--checkpoint.period 2:2:1" in self._chunk_cfg(s, 0, 2)
        assert calls["chunks"] == [(0, 2, True)]
        assert any("auto-scheduled a checkpoint" in m for m in caplog.messages)

    def test_add_checkpoint_false_silences(self, sim, caplog):
        s, calls = sim
        with caplog.at_level(logging.WARNING):
            s.step(nsteps=2, add_checkpoint=False)
        assert "--checkpoint.period" not in self._chunk_cfg(s, 0, 2)
        assert calls["chunks"] == [(0, 2, False)]
        assert not any("auto-scheduled a checkpoint" in m for m in caplog.messages)

    def test_user_checkpoint_covering_end_silences(self, tmp_path, monkeypatch, caplog):
        calls = _stub_step_exec(monkeypatch)
        s = _make_sim(tmp_path, diagnostics=[Checkpoint(period=TimeStepSpec[2], directory="ckpts", file="chk")])
        with caplog.at_level(logging.WARNING):
            s.step(nsteps=2)
        cfg = self._chunk_cfg(s, 0, 2)
        # user's period kept; no forced second write; not merged
        assert cfg.count("--checkpoint.period") == 1
        assert "--checkpoint.period 2:2:1" in cfg
        assert "2:2:1,2:2:1" not in cfg
        assert calls["chunks"] == [(0, 2, False)]
        assert not any("auto-scheduled a checkpoint" in m for m in caplog.messages)

    def test_user_checkpoint_not_covering_end_warns_and_merges(self, tmp_path, monkeypatch, caplog):
        _stub_step_exec(monkeypatch)
        s = _make_sim(tmp_path, diagnostics=[Checkpoint(period=TimeStepSpec[4], directory="ckpts", file="chk")])
        with caplog.at_level(logging.WARNING):
            s.step(nsteps=2)
        cfg = self._chunk_cfg(s, 0, 2)
        # auto at end=2 merged into the user's 4:4:1 (single period flag)
        assert "--checkpoint.period 4:4:1,2:2:1" in cfg
        assert cfg.count("--checkpoint.period") == 1
        assert any("auto-scheduled a checkpoint" in m for m in caplog.messages)


class TestDetectLatestCheckpoint:
    def test_none_when_absent(self, tmp_path, monkeypatch):
        _stub_step_exec(monkeypatch)
        s = _make_sim(tmp_path)
        assert s.picongpu_get_runner().detect_latest_checkpoint() is None

    def test_reads_master_file(self, tmp_path, monkeypatch):
        _stub_step_exec(monkeypatch)
        s = _make_sim(tmp_path)
        r = s.picongpu_get_runner()
        master = r.run_dir / "simOutput" / r.checkpoint_directory
        master.mkdir(parents=True)
        (master / "checkpoints.txt").write_text("0\n2\n4\n")
        assert r.detect_latest_checkpoint() == 4

    def test_fresh_restart_defaults_to_latest_checkpoint(self, tmp_path, monkeypatch):
        calls = _stub_step_exec(monkeypatch)
        s = _make_sim(tmp_path)
        r = s.picongpu_get_runner()
        master = r.run_dir / "simOutput" / r.checkpoint_directory
        master.mkdir(parents=True)
        (master / "checkpoints.txt").write_text("0\n2\n")
        # a fresh sim (0 steps completed) resumes at the latest checkpoint (2)
        s.step(nsteps=2)
        assert calls["chunks"] == [(2, 4, True)]
