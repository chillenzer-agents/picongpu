/* SPDX-FileCopyrightText: 2015-2024 Alexander Grund
 * SPDX-License-Identifier: GPL-3.0-or-later OR LGPL-3.0-or-later
 */

#pragma once

#include "pmacc/types.hpp"

namespace pmacc
{
    namespace errorHandlerPolicies
    {
        /** Returns the given type
         *  Binary meta function that takes any boost mpl sequence and a type
         */
        template<typename T_ReturnType = void>
        struct ReturnType
        {
            template<typename T_MPLSeq, typename T_Value>
            struct apply
            {
                using type = T_ReturnType;
            };
        };

    } // namespace errorHandlerPolicies
} // namespace pmacc
