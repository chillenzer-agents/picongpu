/* SPDX-FileCopyrightText: 2013-2024 Heiko Burau, Rene Widera, Benjamin Worpitz
 * SPDX-License-Identifier: GPL-3.0-or-later OR LGPL-3.0-or-later
 */

#pragma once

#include "pmacc/types.hpp"

namespace pmacc
{
    namespace math
    {
        namespace operation
        {
            struct Assign
            {
                template<typename Dst, typename Src>
                HDINLINE constexpr void operator()(Dst& dst, Src const& src) const
                {
                    dst = src;
                }

                template<typename Dst, typename Src, typename T_Worker>
                HDINLINE constexpr void operator()(T_Worker const&, Dst& dst, Src const& src) const
                {
                    dst = src;
                }
            };
        } // namespace operation
    } // namespace math
} // namespace pmacc
