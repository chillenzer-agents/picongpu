/* SPDX-FileCopyrightText: 2013-2024 Axel Huebl, Felix Schmitt, Heiko Burau
 * SPDX-FileCopyrightText: 2013-2024 Rene Widera, Richard Pausch
 * SPDX-FileCopyrightText: 2013-2024 Alexander Debus, Marco Garten
 * SPDX-FileCopyrightText: 2013-2024 Benjamin Worpitz, Alexander Grund
 * SPDX-FileCopyrightText: 2013-2024 Sergei Bastrakov
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#pragma once

#include "picongpu/fields/FieldJ.hpp"

#include <pmacc/Environment.hpp>
#include <pmacc/dataManagement/DataConnector.hpp>

#include <cstdint>

namespace picongpu
{
    namespace simulation
    {
        namespace stage
        {
            //! Functor for the stage of the PIC loop setting the current values to zero
            struct CurrentReset
            {
                /** Set all current density values to zero
                 *
                 * @param step index of time iteration
                 */
                void operator()(uint32_t const) const
                {
                    using namespace pmacc;
                    DataConnector& dc = Environment<>::get().DataConnector();
                    auto& fieldJ = *dc.get<FieldJ>(FieldJ::getName());
                    FieldJ::ValueType zeroJ(FieldJ::ValueType::create(0._X));
                    fieldJ.assign(zeroJ);
                }
            };

        } // namespace stage
    } // namespace simulation
} // namespace picongpu
