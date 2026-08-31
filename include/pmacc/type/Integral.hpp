/* SPDX-FileCopyrightText: 2013-2024 Felix Schmitt, Heiko Burau, Rene Widera
 * SPDX-FileCopyrightText: 2013-2024 Wolfgang Hoenig, Benjamin Worpitz
 * SPDX-FileCopyrightText: 2013-2024 Alexander Grund
 * SPDX-License-Identifier: GPL-3.0-or-later OR LGPL-3.0-or-later
 */

#pragma once

#include <cstdint>

namespace pmacc
{
    namespace type
    {
        using id_t = uint64_t;
        using uint64_cu = unsigned long long int;
        using int64_cu = long long int;

    } // namespace type

    // for backward compatibility pull all definitions into the pmacc namespace
    using namespace type;
} // namespace pmacc
