/* SPDX-FileCopyrightText: 2021-2024 Sergei Bastrakov
 * SPDX-License-Identifier: GPL-3.0-or-later OR LGPL-3.0-or-later
 */

#pragma once

#include <cstdint>

namespace pmacc
{
    namespace particles
    {
        namespace policies
        {
            //! Policy for HandleGuardParticles that does nothing
            struct DoNothing
            {
                template<typename T_Particles>
                void handleOutgoing(T_Particles& par, int32_t direction) const
                {
                }

                template<typename T_Particles>
                void handleIncoming(T_Particles& par, int32_t direction) const
                {
                }
            };

        } // namespace policies
    } // namespace particles
} // namespace pmacc
