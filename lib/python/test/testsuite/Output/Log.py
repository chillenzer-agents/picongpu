"""
This file is part of PIConGPU.

Copyright 2022-2024 PIConGPU contributors
Authors: Mika Soren Voss
License: GPLv3+

Test suite log files

Routines in this module:

resultLog(direction:str = None, title:str = None)
errorLog()
"""

__all__ = ["errorLog", "resultLog"]

import sys
from time import localtime, strftime

import testsuite._checkData as cD


def resultLog(
    theory: float,
    value_sim: float,
    acceptance: float,
    perc_diff: int,
    result: bool,
    difference: float,
    direction: str | None = None,
    title: str | None = None,
    inputparameter=None,
):
    """
    Creates the file testresult.log, in which all essential
    parameters of the test and the result of the test are
    summarized.

    Input:
    -------
    theory :    float
                Value from the theory against which it was tested

    value_sim : float
                Value from the simulation against which it was tested

    acceptance : float
                 maximum deviation from the theoretical value in
                 percent

    perc_diff : int

    result :    bool
                result of the test, True if passed, otherwise False

    difference : float
                 difference between theory and value_sim

    direction : str, optional
                The directory in which the log file should be saved.
                If None or set in config.py, the value from config.py is
                used.

    title :     str, optional
                Description of the test case. If None or set in
                config.py, the value from config.py is used. If the title
                was not set at all, "no title" is used.

    inputparameter: dict, optional
                    all parameter that are used from the testsuite

    Raise:
    -------
    ValueError :
        If both values (direction and config.resultDirection) are None

    Example of testresult.log:
    -------

    date: 18.08.2022  time: 13:20:38

    Testcase: KHI Growthrate
    Theoretically expected value: 0.34662097116987617
    Value from simulation: 0.3473760369365579
    Acceptance range: (0.27729677693590093, 0.4159451654038514)
    Result of the test: passed
    Difference: -0.0007550657666817173
    Difference in percentage: -0.21736265211051872 %

    """

    try:
        lt = localtime()
        date = strftime("date: %d.%m.%Y", lt)
        timeOfDay = strftime("time: %H:%M:%S", lt)

        title = cD.checkVariables(variable="title", default="No title", parameter=title)

        direction = cD.checkDirection(variable="resultDirection", direction=direction)

        with open(direction + "/testresult.log", "w+") as fobj_out:
            fobj_out.write(date + " " + timeOfDay + "\n")
            fobj_out.write("\n")
            fobj_out.write("testcase: " + title + "\n")
            fobj_out.write(f"theoretically expected value: {theory}\n")
            fobj_out.write(f"Value from simulation: {value_sim}\n")
            fobj_out.write(f"acceptance: {acceptance}\n")
            fobj_out.write(f"result of the test:{result} \n")
            fobj_out.write(f"difference: {difference}\n")
            fobj_out.write(f"difference in percentage: {perc_diff}\n")
            fobj_out.writelines(f"input parameter: {key}={inputparameter[key]}\n" for key in inputparameter)

    except Exception:
        errorLog()


def errorLog(direction: str | None = None):
    """
    Catches errors while executing the test-suite and saves
    them in the error.log file.

    Input:
    -------
    direction : str, optional
                The directory in which the error log file should be
                saved. If None or set in config.py, the value from
                config.py is used. If both are not set or the directory
                does not exist, the current working directory is used.
    """

    direction = cD.checkDirection(variable="resultDirection", direction=direction, errorhandling=True)

    lt = localtime()
    date = strftime("date: %d.%m.%Y", lt)
    timeOfDay = strftime("time: %H:%M:%S", lt)

    error0 = str(sys.exc_info()[0])
    error1 = str(sys.exc_info()[1])
    error2 = str(sys.exc_info()[2])

    # print error0 + error1 + error2
    with open(direction + "/error.log", "w") as fobj_out:
        fobj_out.write(date + " " + timeOfDay + "\n")
        fobj_out.write("\n")
        fobj_out.write(error0 + " " + error1 + " " + error2 + "\n")

    sys.exit(42)


# ToDo usedDatalog
