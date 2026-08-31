"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: AI agent (task 11, EFP/LEXIS submission config)
License: GPLv3+
"""

import json
import os
import re
import subprocess
import sys
from copy import deepcopy

from moosetash import MissingVariable
from picongpu import core, rc_params
from picongpu._rc_params import RCParams, get_available_presets
from picongpu.picmi import Cartesian3DGrid, ElectromagneticSolver, Simulation
from pytest import fixture, raises

EFP_PRESET = "efp-jupiter-jsc"
EFP_TPL = "etc/picongpu/efp-jupiter-jsc/gh200_efp.tpl"


def test_efp_preset_is_discovered():
    assert f"{EFP_PRESET}/efp_picongpu.profile.example" in get_available_presets()


def test_efp_preset_resolves_unambiguously():
    assert RCParams(preset=EFP_PRESET).preset_dir == EFP_PRESET
    # the short name is unambiguous, too
    assert RCParams(preset="efp")["tbg_tpl_file"] == EFP_TPL
    # the pre-existing system preset must not become ambiguous:
    assert RCParams(preset="jupiter-jsc/gh200_picongpu").preset_dir == "jupiter-jsc"


JUPITER_TPL = "etc/picongpu/jupiter-jsc/gh200.tpl"


def test_pre_existing_jupiter_preset_selections_still_resolve():
    # Regression test: the "efp-jupiter-jsc/" preset path contains the
    # pre-existing "jupiter-jsc" preset name, so with a plain substring
    # matcher every short selection of the pre-existing preset would raise
    # a "ambiguous" ValueError. They must keep resolving to jupiter-jsc:
    assert RCParams(preset="jupiter-jsc").preset_dir == "jupiter-jsc"
    assert RCParams(preset="jupiter-jsc")["tbg_tpl_file"] == JUPITER_TPL
    assert RCParams(preset="jupiter")["tbg_tpl_file"] == JUPITER_TPL
    assert RCParams(preset="jup")["tbg_tpl_file"] == JUPITER_TPL
    # ... while the EFP preset resolves for its own names:
    assert RCParams(preset=EFP_PRESET)["tbg_tpl_file"] == EFP_TPL
    assert RCParams(preset="efp")["tbg_tpl_file"] == EFP_TPL
    # and genuinely ambiguous selections still raise:
    with raises(ValueError):
        RCParams(preset="jsc")


def test_efp_preset_submission_defaults():
    rc = RCParams(preset=EFP_PRESET)
    assert rc["tbg_submit"] == "sbatch"
    assert rc["tbg_tpl_file"] == EFP_TPL
    assert rc["pic_backend"] == "cuda:90"


def test_efp_preset_rendering_requires_user_information():
    rc = RCParams(preset=EFP_PRESET)
    assert "author" in rc["required_information"]
    assert "email" in rc["required_information"]
    with raises(MissingVariable):
        rc.profile_content


def _render_efp_tpl(tmp_path, extra_args=()):
    cfg = tmp_path / "N.cfg"
    cfg.write_text('TBG_wallTime="00:10:00"\nTBG_tasks=4\nTBG_programParams="--versionOnce"\n')
    result = subprocess.run(
        [
            str(core.path("bin") / "tbg"),
            "-c",
            str(cfg),
            "-t",
            str(core.path("etc") / "picongpu" / EFP_PRESET / "gh200_efp.tpl"),
            *extra_args,
            str(tmp_path / "run"),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return (tmp_path / "run" / "tbg" / "submit.start").read_text()


def test_efp_tpl_renders_self_contained_job_script(tmp_path):
    submit_start = _render_efp_tpl(tmp_path)
    # no unresolved template variables
    assert not re.search(r"![A-Za-z]", submit_start)
    # self-contained: pins the working directory without hard-coding it
    assert 'TBG_dstPath="$(pwd)"' in submit_start
    assert "--chdir=" not in submit_start
    # sources the profile shipped with the input dataset
    assert "input/picongpu.profile" in submit_start
    # launches the executable staged with the input dataset
    assert "$TBG_dstPath/input/bin/picongpu" in submit_start
    # keeps the SLURM resource requests (4 tasks, 4 GPUs per node)
    assert re.search(r"^#SBATCH --ntasks=4", submit_start, re.MULTILINE)
    assert re.search(r"^#SBATCH --nodes=1", submit_start, re.MULTILINE)
    assert re.search(r"^#SBATCH --gres=gpu:4", submit_start, re.MULTILINE)


def test_efp_tpl_supports_overwrite_vars(tmp_path):
    submit_start = _render_efp_tpl(tmp_path, extra_args=("-o", "TBG_queue=debug TBG_wallTime=01:00:00"))
    assert re.search(r"^#SBATCH --partition=debug", submit_start, re.MULTILINE)
    assert re.search(r"^#SBATCH --time=01:00:00", submit_start, re.MULTILINE)


@fixture
def efp_rc_params():
    previous = deepcopy(rc_params._data)
    rc_params["preset"] = EFP_PRESET
    rc_params["author"] = "EFP Test"
    rc_params["email"] = "efp-test@example.com"
    rc_params["pic_libs"] = "/projappl/efp-test/lib"
    yield rc_params
    rc_params._data = previous


def test_efp_preset_generate_copies_preset_and_drives_flags(efp_rc_params):
    number_of_cells = 32
    sim = Simulation(
        time_step_size=17,
        max_steps=4,
        solver=ElectromagneticSolver(
            method="Yee",
            grid=Cartesian3DGrid(
                number_of_cells=[number_of_cells] * 3,
                lower_bound=[0, 0, 0],
                upper_bound=[number_of_cells] * 3,
                lower_boundary_conditions=["open", "open", "periodic"],
                upper_boundary_conditions=["open", "open", "periodic"],
            ),
        ),
    )
    runner = sim.picongpu_get_runner()
    runner.generate()
    preset_dir = runner.setup_dir / "etc" / "picongpu" / EFP_PRESET
    assert (preset_dir / "gh200_efp.tpl").is_file()
    assert (preset_dir / "efp_picongpu.profile.example").is_file()
    # the bare profile is rendered into the setup and selects the EFP template
    assert EFP_TPL in runner.profile_path.read_text()
    # the CWL workflow inputs carry the EFP submission settings
    inputs = json.loads(runner.workflow_input_path.read_text())
    assert inputs["run_submit_system"] == "sbatch"
    assert inputs["run_template_file"] == EFP_TPL


def test_laptop_flow_discovers_rc_file_next_to_picmi_script(tmp_path):
    # The documented primary laptop route: a picongpurc.toml next to the
    # PICMI script must actually select the preset (review finding M1: with
    # a dotfile-only CWD glob this silently produced a setup without the
    # EFP preset).
    (tmp_path / "picongpurc.toml").write_text(
        f'preset = "{EFP_PRESET}"\n'
        'author = "EFP Test"\n'
        'email = "efp-test@example.com"\n'
        f'pic_src_path = "{core.path()}"\n'
        f'pic_libs = "{tmp_path}"\n'
    )
    (tmp_path / "sim.py").write_text(
        "from picongpu.picmi import Cartesian3DGrid, ElectromagneticSolver, Simulation\n"
        "sim = Simulation(time_step_size=1, max_steps=1, solver=ElectromagneticSolver(method='Yee', grid="
        "Cartesian3DGrid(number_of_cells=[16] * 3, lower_bound=[0] * 3, upper_bound=[16] * 3, "
        "lower_boundary_conditions=['periodic'] * 3, upper_boundary_conditions=['periodic'] * 3)))\n"
        "sim.write_input_file('setup')\n"
    )
    env = {key: value for key, value in os.environ.items() if key != "PIC_RC"}
    result = subprocess.run([sys.executable, "sim.py"], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    # the EFP preset was applied through CWD discovery:
    assert (tmp_path / "setup" / "etc" / "picongpu" / EFP_PRESET / "gh200_efp.tpl").is_file()
    assert EFP_TPL in (tmp_path / "setup" / "workflow" / "scripts" / "picongpu.profile").read_text()
