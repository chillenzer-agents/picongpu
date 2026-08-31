/* SPDX-FileCopyrightText: 2013-2024 Rene Widera
 * SPDX-License-Identifier: GPL-3.0-or-later OR LGPL-3.0-or-later
 */

#pragma once

namespace pmacc
{
    namespace traits
    {
        template<typename T>
        struct GetValueType
        {
            using ValueType = typename T::ValueType;
        };
    } // namespace traits
} // namespace pmacc

#include "GetValueType.tpp"
