/* SPDX-FileCopyrightText: 2013-2024 Felix Schmitt, Heiko Burau, Rene Widera
 * SPDX-FileCopyrightText: 2013-2024 Wolfgang Hoenig, Benjamin Worpitz
 * SPDX-FileCopyrightText: 2013-2024 Alexander Grund
 * SPDX-License-Identifier: GPL-3.0-or-later OR LGPL-3.0-or-later
 */

#pragma once

#include <cstdint>

namespace pmacc
{
    namespace eventSystem
    {
        /**
         * Internal event/task type used for notifications in the event system.
         */
        enum EventType
        {
            FINISHED,
            COPY,
            SENDFINISHED,
            RECVFINISHED,
            LOGICALAND,
            SETVALUE,
            GETVALUE,
            KERNEL,
            SIGNAL
        };

    } // namespace eventSystem

    // for backward compatibility pull all definitions into the pmacc namespace
    using namespace eventSystem;
} // namespace pmacc
