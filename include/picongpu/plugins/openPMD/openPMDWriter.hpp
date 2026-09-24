/* SPDX-FileCopyrightText: 2014-2024 Axel Huebl, Felix Schmitt, Heiko Burau
 * SPDX-FileCopyrightText: 2014-2024 Rene Widera, Benjamin Worpitz
 * SPDX-FileCopyrightText: 2014-2024 Alexander Grund, Franz Poeschel
 * SPDX-FileCopyrightText: 2014-2024 Pawel Ordyna, Sergei Bastrakov
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#pragma once

#if (ENABLE_OPENPMD == 1)

#    include "picongpu/plugins/multi/IHelp.hpp"

#    include <memory>

namespace picongpu
{
    namespace openPMD
    {
        std::shared_ptr<plugins::multi::IHelp> getOpenPMDWriterHelp();
    } // namespace openPMD
} // namespace picongpu

#endif
