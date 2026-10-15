.. _testing-usage:

How to use the test suite
=========================

As already mentioned, the test suite can be used in two different ways.
On the one hand, the automatic validation is based on a given test case.
This is mainly required for new methods within the code to check their correctness.
If a test is simulated manually, only the associated bashscript has to be executed.

.. note::

    When running the bashscript, an output folder is created, labeled with the current date.
    This folder contains all essential data of the test including the test result.
    By default, this folder is kept and only the result is reported to the system as an exit code
    (0 = passed, 1 = failed, 42 = error).
    Pass ``--delete`` to remove the folder after the test has been run.

On the other hand, the test suite should also be able to be used to evaluate existing simulations.
No ci.bash needs to be executed for this.
Instead, it is advisable to run the main.py of the respective test directly.

.. code-block:: bash
   :emphasize-lines: 1

   python lib/python/test/setups/ESKHI/main.py --help
