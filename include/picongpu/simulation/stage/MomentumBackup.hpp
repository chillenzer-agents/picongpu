/* SPDX-FileCopyrightText: 2013-2024 Axel Huebl, Felix Schmitt, Heiko Burau
 * SPDX-FileCopyrightText: 2013-2024 Rene Widera, Richard Pausch
 * SPDX-FileCopyrightText: 2013-2024 Alexander Debus, Marco Garten
 * SPDX-FileCopyrightText: 2013-2024 Benjamin Worpitz, Alexander Grund
 * SPDX-FileCopyrightText: 2013-2024 Sergei Bastrakov
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#pragma once

#include "picongpu/particles/Manipulate.def"
#include "picongpu/particles/param.hpp"

#include <pmacc/particles/traits/FilterByIdentifier.hpp>

#include <cstdint>

namespace picongpu
{
    namespace simulation
    {
        namespace stage
        {
            /** Functor for the stage of the PIC loop copying particles' momentums
             *  to momentumPrev1
             *
             * Only affects particle species with the momentumPrev1 attribute.
             */
            struct MomentumBackup
            {
                /** Copy the momentums
                 *
                 * @param step index of time iteration
                 */
                void operator()(uint32_t const step) const
                {
                    using pmacc::particles::traits::FilterByIdentifier;
                    using SpeciesWithMomentumPrev1 =
                        typename FilterByIdentifier<VectorAllSpecies, momentumPrev1>::type;
                    using CopyMomentum = particles::manipulators::unary::CopyAttribute<momentumPrev1, momentum>;
                    particles::manipulate<CopyMomentum, SpeciesWithMomentumPrev1>(step);
                }
            };

        } // namespace stage
    } // namespace simulation
} // namespace picongpu
