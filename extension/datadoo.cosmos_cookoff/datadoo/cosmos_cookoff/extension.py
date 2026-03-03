# SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

import omni.ext
import omni.kit.menu.utils

class CosmosCookoffExt(omni.ext.IExt, omni.kit.menu.utils.MenuHelperExtensionFull):
    def on_startup(self, _ext_id):
        import datadoo.cosmos_cookoff.cosmos_cookoff as datadoo_cosmos_cookoff
        import datadoo.cosmos_cookoff.cosmos_cookoff_ui as datadoo_cosmos_cookoff_ui

        self.cosmos_cookoff = datadoo_cosmos_cookoff.CosmosCookoff()
        self.cosmos_cookoff_ui = datadoo_cosmos_cookoff_ui.CosmosCookoffUI(self.cosmos_cookoff)
        self.cosmos_cookoff_ui.show_ui()
        self.cosmos_cookoff_ui.setup()

    def on_shutdown(self):
        self.cosmos_cookoff_ui.finish()

