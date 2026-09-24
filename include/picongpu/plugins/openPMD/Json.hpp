/* SPDX-FileCopyrightText: 2021-2024 Franz Poeschel
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#pragma once

#include <string>

#include <mpi.h>

namespace picongpu::openPMD
{
    auto resolveJsonConfig(std::string const& commandLineValue, MPI_Comm) -> std::string;
} // namespace picongpu::openPMD
