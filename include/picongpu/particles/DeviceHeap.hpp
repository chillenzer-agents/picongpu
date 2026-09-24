/* SPDX-FileCopyrightText: 2013-2024 Axel Huebl, Heiko Burau, Rene Widera
 * SPDX-FileCopyrightText: 2013-2024 Felix Schmitt, Marco Garten
 * SPDX-FileCopyrightText: 2013-2024 Alexander Grund, Sergei Bastrakov
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#pragma once

#include "picongpu/defines.hpp"

namespace picongpu
{
    using namespace pmacc;

#if (!ALPAKA_LANG_CUDA && !ALPAKA_COMP_HIP)
    /* dummy because we are not using mallocMC with CPU backends
     * DeviceHeap is defined in `mallocMC.param`
     */
    struct DeviceHeap
    {
        using AllocatorHandle = int;

        int getAllocatorHandle()
        {
            return 0;
        }
    };
#endif
} // namespace picongpu
