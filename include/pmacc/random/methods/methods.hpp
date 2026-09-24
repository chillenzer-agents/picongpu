/* SPDX-FileCopyrightText: 2018-2024 Rene Widera
 * SPDX-License-Identifier: GPL-3.0-or-later OR LGPL-3.0-or-later
 */

#pragma once

#include "pmacc/random/methods/AlpakaRand.hpp"
#ifndef ALPAKA_DISABLE_VENDOR_RNG
#    include "pmacc/random/methods/MRG32k3aMin.hpp"
#    include "pmacc/random/methods/XorMin.hpp"
#endif
