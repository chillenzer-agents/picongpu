/* SPDX-FileCopyrightText: 2024-2024 Rene Widera
 * SPDX-License-Identifier: GPL-3.0-or-later OR LGPL-3.0-or-later
 */


#pragma once

#include "pmacc/math/functions/Common.hpp"

#include <alpaka/alpaka.hpp>

namespace pmacc::math
{
    //! Computes the value of base raised to the power exp.
    ALPAKA_BINARY_MATH_FN(pow, alpaka::math::ConceptMathPow, Pow)

} // namespace pmacc::math
