/* SPDX-FileCopyrightText: 2023-2024 Tapish Narwal
 * SPDX-License-Identifier: GPL-3.0-or-later OR LGPL-3.0-or-later
 */

## Installing
- Make a build directory
- cmake ..
- ccmake .
    - choose accelerator backend, configure and generate
- cmake --build .

## Running
- mpirun -npernode 4 -n 4 ./heatEq
    - make sure that -npernode and -n are set according to the number of devices in the code, when you initialize the pmacc::Environment
