# PIConGPU Python package

Python front-end and input API for
[PIConGPU](https://github.com/ComputationalRadiationPhysics/picongpu),
the fully relativistic particle-in-cell code.

```sh
pip install picongpu
```

This package generates and submits PIConGPU input and ships the PIConGPU C++
sources, example setups and build scripts (`pic-create`, `pic-build`). It
contains **no pre-built simulation binary**: running a simulation still requires
compiling PIConGPU for your backend (CUDA, HIP or CPU).

## Documentation

- Full documentation: <https://picongpu.readthedocs.io/en/latest/>
- Repository, build instructions and the project README:
  <https://github.com/ComputationalRadiationPhysics/picongpu#readme>
