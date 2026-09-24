/* SPDX-FileCopyrightText: 2023-2024 Rene Widera
 * SPDX-License-Identifier: GPL-3.0-or-later OR LGPL-3.0-or-later
 */


#pragma once

namespace pmacc::eventSystem
{
    /** Blocks the event system until all tasks finished */
    void waitForAllTasks();
} // namespace pmacc::eventSystem
