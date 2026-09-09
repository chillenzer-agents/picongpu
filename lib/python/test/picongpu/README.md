# PIConGPU Python Test Suite

This directory contains the test suite for the Python bindings of PIConGPU.

## Test Categories

### Quick Tests (`quick/`)
Fast unit tests that run in seconds. Used for CI on every commit.

**Run:** `pytest quick/`

### Compiling Tests (`compiling/`)
Tests that compile PIConGPU simulations. Long-running, requires build tools (cmake, boost, C++ compiler).

**Run:** `pytest -m compiling`
**Mark:** `@pytest.mark.slow`, `@pytest.mark.compiling`

### End-to-End Tests (`end_to_end/`)
Full simulation tests comparing output against reference data.

**Run:** `pytest -m end_to_end`
**Mark:** `@pytest.mark.slow`, `@pytest.mark.end_to_end`

## Running Tests

```bash
# Install test dependencies
pip install -e ".[test]"

# Run quick tests only (default for CI)
pytest quick/
pytest -m "not slow"  # equivalent

# Run all tests including slow ones
pytest

# Run only slow tests
pytest -m slow

# Run specific category
pytest -m compiling
pytest -m end_to_end
```

## Test Markers

- `slow` - long-running tests (compiling, end-to-end)
- `compiling` - tests that compile PIConGPU simulations
- `end_to_end` - full simulation tests with reference comparison

Markers are automatically applied based on test directory location via `conftest.py`.

## How CI selects the suites

All Python CI jobs run the quick suite via the directory path (`pytest quick/`),
which is the default and cannot pick up slow tests. The slow suites are selected
by marker so that selection is guaranteed to match the documentation:

- `pypicongpu-compiling-test` (`PYTHON_COMPILING_TEST=ON`) -> `pytest -m compiling`
- `pypicongpu-end-to-end-test` (`PYTHON_END_TO_END_TEST=ON`) -> `pytest -m end_to_end`

Both slow jobs are skipped when the `ci: no-compile` / `CI:no-compile` /
`ci: no-python-compile` flags are set (see `share/ci/ci_flags.sh`).

## Per-example opt-out

Any example script (`lib/python/examples/*/main.py`) can opt out of the
compiling suite by declaring a whole-line `# ci: no-compile` comment. Such
examples are skipped by `pytest -m compiling` (marked `ci_no_compile`, so also
deselectable with `-m "not ci_no_compile"`) while remaining generatable and
compilable locally by hand.
