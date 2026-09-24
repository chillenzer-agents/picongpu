/* SPDX-FileCopyrightText: 2013-2024 Axel Huebl, Felix Schmitt, Heiko Burau
 * SPDX-FileCopyrightText: 2013-2024 Rene Widera, Richard Pausch
 * SPDX-FileCopyrightText: 2013-2024 Alexander Debus, Marco Garten
 * SPDX-FileCopyrightText: 2013-2024 Benjamin Worpitz, Alexander Grund
 * SPDX-FileCopyrightText: 2013-2024 Sergei Bastrakov
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#pragma once

#include <cstdint>

namespace picongpu
{
    namespace simulation
    {
        namespace stage
        {
            //! Functor for the stage of the PIC loop performing current deposition
            struct CurrentDeposition
            {
                /** Compute the current created by particles and add it to the current
                 *  density
                 *
                 * @param step index of time iteration
                 */
                void operator()(uint32_t const step) const;
            };

        } // namespace stage
    } // namespace simulation
} // namespace picongpu
