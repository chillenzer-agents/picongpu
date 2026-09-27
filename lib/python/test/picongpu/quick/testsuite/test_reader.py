"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: opencode
License: GPLv3+

Unit tests for the Reader classes of the standalone post-simulation
validation framework (lib/python/test/testsuite/Reader) against small
fixture files.
"""

import gc
import json
import warnings

import numpy as np
import pytest

with warnings.catch_warnings():
    # importing testsuite falls back to the template config and warns
    warnings.simplefilter("ignore")
    from testsuite.Reader import cmakeFlagReader
    from testsuite.Reader import dataReader
    from testsuite.Reader import jsonReader
    from testsuite.Reader import paramReader
    from testsuite.Reader import readFiles


class TestReadFiles:
    def test_requires_direction(self):
        with pytest.raises(TypeError):
            readFiles.ReadFiles(fileExtension=".dat")

    def test_getters(self):
        rf = readFiles.ReadFiles(fileExtension=".dat", direction="/tmp")
        assert rf.getDirection() == "/tmp/"
        assert rf.getFileExtension() == ".dat"

    def test_set_direction(self, tmp_path):
        # regression test: setDirection used to raise AttributeError
        rf = readFiles.ReadFiles(fileExtension=".dat", direction="/tmp", directiontype="test_set_direction")
        # the constructor persists the directory into the (global) template
        # config; per the docstring, reset the directiontype before re-setting
        rf.setDirectiontype("test_set_direction_reset")
        rf.setDirection(str(tmp_path))
        assert rf.getDirection() == str(tmp_path) + "/"

    def test_check_files_and_get_all(self, tmp_path):
        (tmp_path / "a.dat").write_text("step Bx\n")
        (tmp_path / "b.json").write_text("{}")
        rf = readFiles.ReadFiles(fileExtension=".dat", direction=str(tmp_path))
        assert rf.checkFilesInDir()
        assert rf.getAllFiles() == ["a.dat"]


class TestParamReader:
    def _make_reader(self, tmp_path, content):
        (tmp_path / "simulation.param").write_text(content)
        return paramReader.ParamReader(direction=str(tmp_path))

    def test_get_value(self, tmp_path):
        reader = self._make_reader(tmp_path, "constexpr float_64 BASE_DENSITY_SI = 1.0e24;\n")
        assert reader.getValue("BASE_DENSITY_SI") == pytest.approx(1.0e24)

    def test_get_value_with_multiplication(self, tmp_path):
        reader = self._make_reader(tmp_path, "constexpr float_64 DELTA_T_SI = 1.79e-16 * 0.86;\n")
        assert reader.getValue("DELTA_T_SI") == pytest.approx(1.79e-16 * 0.86)

    def test_get_param(self, tmp_path):
        reader = self._make_reader(tmp_path, "constexpr float_64 GAMMA = 2.0;\n")
        assert reader.getParam("GAMMA") == ["simulation.param"]

    def test_get_value_missing(self, tmp_path):
        reader = self._make_reader(tmp_path, "constexpr float_64 GAMMA = 2.0;\n")
        with pytest.raises(ValueError):
            reader.getValue("MISSING")


class TestCMAKEFlagReader:
    # regression test (task-10 review m2): getAllSetups opened the
    # cmakeFlags file without closing it; under filterwarnings=error the
    # resulting ResourceWarning fails any test exercising it

    def _make_reader(self, tmp_path):
        (tmp_path / "cmakeFlags").write_text(
            'flags[0]="-DPIC_GAMMA=1.021;-DPIC_DENSITY=1.0e25"\n'
            'flags[1]="-DPIC_GAMMA=1.0;-DPIC_DENSITY=2.0e25"\n'
        )
        (tmp_path / "cmakeFlagsSetup").write_text("selected setup:0\n")
        return cmakeFlagReader.CMAKEFlagReader(direction=str(tmp_path))

    def test_get_all_setups(self, tmp_path):
        reader = self._make_reader(tmp_path)
        assert reader.getAllSetups() == [
            "-DPIC_GAMMA=1.021;-DPIC_DENSITY=1.0e25",
            "-DPIC_GAMMA=1.0;-DPIC_DENSITY=2.0e25",
        ]
        # force collection of any file handle left open by getAllSetups; an
        # unclosed handle would raise a ResourceWarning -> error here
        gc.collect()

    def test_used_setup(self, tmp_path):
        reader = self._make_reader(tmp_path)
        assert reader.usedSetup() == 0

    def test_get_value(self, tmp_path):
        reader = self._make_reader(tmp_path)
        assert reader.getValue("PIC_GAMMA") == pytest.approx(1.021)


class TestDataReader:
    def _make_reader(self, tmp_path):
        data = np.column_stack((np.arange(4.0), 2.0 ** np.arange(4.0), 3.0 ** np.arange(4.0)))
        with open(tmp_path / "fields_energy.dat", "w") as fh:
            fh.write("step Bx By\n")
            np.savetxt(fh, data)
        return dataReader.DataReader(direction=str(tmp_path))

    def test_all_params_in_file(self, tmp_path):
        reader = self._make_reader(tmp_path)
        assert reader.allParamsinFile(str(tmp_path / "fields_energy.dat"))[:2] == ["step", "Bx"]

    def test_get_value_step(self, tmp_path):
        reader = self._make_reader(tmp_path)
        np.testing.assert_allclose(reader.getValue("step"), [0.0, 1.0, 2.0, 3.0])

    def test_get_value_column(self, tmp_path):
        reader = self._make_reader(tmp_path)
        np.testing.assert_allclose(reader.getValue("Bx"), [1.0, 2.0, 4.0, 8.0])

    def test_get_datwith_param(self, tmp_path):
        reader = self._make_reader(tmp_path)
        assert reader.getDatwithParam("Bx") == ["fields_energy.dat"]
        assert reader.getDatwithParam("Bz") == []


class TestDataReaderTrailingColumn:
    # regression test (task-10 review m1): allParamsinFile used to keep the
    # trailing newline of the header line on the last column name
    # ("Bx\n" != "Bx"), so a sought parameter that is the last header column
    # was never found and getValue raised "could not be found"

    def _make_reader(self, tmp_path):
        data = np.column_stack((np.arange(4.0), 2.0 ** np.arange(4.0)))
        with open(tmp_path / "fields_energy.dat", "w") as fh:
            fh.write("step Bx\n")
            np.savetxt(fh, data)
        return dataReader.DataReader(direction=str(tmp_path))

    def test_all_params_in_file(self, tmp_path):
        reader = self._make_reader(tmp_path)
        assert reader.allParamsinFile(str(tmp_path / "fields_energy.dat")) == ["step", "Bx"]

    def test_get_datwith_param(self, tmp_path):
        reader = self._make_reader(tmp_path)
        assert reader.getDatwithParam("Bx") == ["fields_energy.dat"]

    def test_get_value_trailing_column(self, tmp_path):
        reader = self._make_reader(tmp_path)
        np.testing.assert_allclose(reader.getValue("Bx"), [1.0, 2.0, 4.0, 8.0])


class TestJSONReader:
    def _make_reader(self, tmp_path):
        (tmp_path / "meta.json").write_text(json.dumps({"gamma": {"values": 2.5}}))
        return jsonReader.JSONReader(direction=str(tmp_path))

    def test_get_value(self, tmp_path):
        assert self._make_reader(tmp_path).getValue("gamma") == 2.5

    def test_get_json_with_param(self, tmp_path):
        reader = self._make_reader(tmp_path)
        assert reader.getJSONwithParam("gamma") == ["meta.json"]
        assert reader.getJSONwithParam("other") == []

    def test_get_value_missing(self, tmp_path):
        with pytest.raises(ValueError):
            self._make_reader(tmp_path).getValue("other")
