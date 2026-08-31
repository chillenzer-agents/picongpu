/* SPDX-FileCopyrightText: 2013-2024 Felix Schmitt, Heiko Burau, Rene Widera
 * SPDX-FileCopyrightText: 2013-2024 Wolfgang Hoenig, Benjamin Worpitz
 * SPDX-FileCopyrightText: 2013-2024 Alexander Grund
 * SPDX-License-Identifier: GPL-3.0-or-later OR LGPL-3.0-or-later
 */

#pragma once


#define BOOST_MPL_LIMIT_VECTOR_SIZE 20
#define BOOST_MPL_LIMIT_MAP_SIZE 20

#include <alpaka/alpaka.hpp>

#if (ALPAKA_LANG_CUDA || ALPAKA_COMP_HIP)
#    include <mallocMC/mallocMC.hpp>
#endif


#include <pmacc/boost_workaround.hpp>

#include "pmacc/alpakaHelper/ValidateCall.hpp"
#include "pmacc/alpakaHelper/acc.hpp"
#include "pmacc/attribute/Constexpr.hpp"
#include "pmacc/attribute/FunctionSpecifier.hpp"
#include "pmacc/debug/PMaccVerbose.hpp"
#include "pmacc/dimensions/Definition.hpp"
#include "pmacc/eventSystem/EventType.hpp"
#include "pmacc/memory/Align.hpp"
#include "pmacc/meta/Mp11.hpp"
#include "pmacc/ppFunctions.hpp"
#include "pmacc/type/Area.hpp"
#include "pmacc/type/Exchange.hpp"
#include "pmacc/type/Integral.hpp"

#include <alpaka/alpaka.hpp>

#include <boost/filesystem.hpp>

namespace pmacc
{
} // namespace pmacc
