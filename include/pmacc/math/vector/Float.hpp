/* SPDX-FileCopyrightText: 2013-2024 Heiko Burau, Rene Widera, Benjamin Worpitz
 * SPDX-License-Identifier: GPL-3.0-or-later OR LGPL-3.0-or-later
 */

#pragma once

#include "Vector.hpp"

namespace pmacc
{
    namespace math
    {
        template<uint32_t dim>
        using Float = Vector<float, dim>;
    } // namespace math
} // namespace pmacc
