/* SPDX-FileCopyrightText: 2015-2024 Alexander Grund
 * SPDX-License-Identifier: GPL-3.0-or-later OR LGPL-3.0-or-later
 */

#pragma once

#include "pmacc/types.hpp"

namespace pmacc
{
    namespace errorHandlerPolicies
    {
        /** Returns the second parameter (normally the value that the sequence was searched for
         *  Binary meta function that takes any boost mpl sequence and a type
         */
        struct ReturnValue
        {
            template<typename T_MPLSeq, typename T_Value>
            struct apply
            {
                using type = T_Value;
            };
        };

    } // namespace errorHandlerPolicies
} // namespace pmacc
