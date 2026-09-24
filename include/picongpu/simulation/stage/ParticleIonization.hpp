/* SPDX-FileCopyrightText: 2013-2024 Axel Huebl, Felix Schmitt, Heiko Burau
 * SPDX-FileCopyrightText: 2013-2024 Rene Widera, Richard Pausch
 * SPDX-FileCopyrightText: 2013-2024 Alexander Debus, Marco Garten
 * SPDX-FileCopyrightText: 2013-2024 Benjamin Worpitz, Alexander Grund
 * SPDX-FileCopyrightText: 2013-2024 Sergei Bastrakov
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#pragma once

#include "picongpu/defines.hpp"

#include <cstdint>

namespace picongpu
{
    namespace simulation
    {
        namespace stage
        {
            /** Functor for the stage of the PIC loop performing particle ionization
             *
             * Only affects particle species with the ionizers attribute.
             */
            class ParticleIonization
            {
            public:
                /** Create a particle ionization functor
                 *
                 * Having this in constructor is a temporary solution.
                 *
                 * @param cellDescription mapping for kernels
                 */
                ParticleIonization(MappingDesc const cellDescription) : cellDescription(cellDescription)
                {
                }

                /** Ionize particles
                 *
                 * @param step index of time iteration
                 */
                void operator()(uint32_t const step) const;

            private:
                //! Mapping for kernels
                MappingDesc cellDescription;
            };

        } // namespace stage
    } // namespace simulation
} // namespace picongpu
