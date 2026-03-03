# SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

import asyncio
import carb
import carb.settings
import logging
import omni.kit.async_engine
import omni.kit.menu.utils
import omni.kit.window
import omni.kit.window.file_importer
import omni.ui as ui
import omni.usd
import sys

from pxr import Usd, UsdShade, Sdf, UsdGeom, Gf

import datadoo.cosmos_cookoff.ui_utils as datadoo_ui_utils
import datadoo.cosmos_cookoff.cosmos_cookoff as datadoo_cosmos_cookoff

class CosmosCookoffUI():
    DEFAULT_HEIGHT_BUTTON = 32
    DEFAULT_HEIGHT_SEPARATOR = 8
    WINDOW_NAME = "Datadoo Cosmos Cookoff"

    def __init__(self, cosmos_cookoff: datadoo_cosmos_cookoff) -> None:
        # Logging
        self.logger = logging.getLogger("CosmosCookOffUI")
        self.logger.addHandler(logging.StreamHandler(sys.stdout))
        self.logger.handlers[0].setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] [%(name)s] %(message)s"))
        self.logger.handlers[0].setLevel(logging.DEBUG)
        
        # Cosmos Cookoff
        self.cosmos_cookoff: datadoo_cosmos_cookoff = cosmos_cookoff
        
        # Omniverse
        self.usd_conext: omni.usd.UsdContext = None
        self.settings: carb.settings.ISettings = None

        # UI
        self.window: ui.Window = None
        self.ui_load_stage_ref: datadoo_ui_utils.ButtonRef = None
        self.ui_reset_ref: datadoo_ui_utils.ButtonRef = None
        self.ui_select_paths_ref: datadoo_ui_utils.ButtonRef = None
        self.ui_auto_drive_ref: datadoo_ui_utils.ButtonRef = None
        self.ui_use_cosmos_ref: datadoo_ui_utils.CheckBoxFieldRef = None
        self.ui_path_list_ref: datadoo_ui_utils.ComboboxRef = None
        self.ui_load_stage_pressed: bool = False
        self.ui_use_cosmos_selected: bool = True

    def show_ui(self):
        self.build_cosmos_cookoff_main_window()

    def setup(self):
        if not self.cosmos_cookoff.setup():
            self.logger.error(f"Failed setting up Datadoo Cosmos Cookoff")

    def finish(self):
        self.cosmos_cookoff.finish()
        if self.window:
            self.window.destroy()

    def build_cosmos_cookoff_main_window(self):
        self.window = ui.Window(title=self.WINDOW_NAME, dockPreference=ui.DockPreference.RIGHT_BOTTOM, visible=True)
        self.window.deferred_dock_in("Property", ui.DockPolicy.DO_NOTHING)
        self.build_cosmos_cookoff_buttons()
        
    def build_cosmos_cookoff_buttons(self):
        with self.window.frame:
            with ui.VStack(spacing=5, height=0):
                label = "Load stage " if not self.ui_load_stage_pressed else "Close stage "
                name = "LOAD" if not self.ui_load_stage_pressed else "CLOSE"
                tooltip = "Load the USD stage for Cosmos Cookoff" if not self.ui_load_stage_pressed else "Close Cosmos Cookoff stage"
                on_clicked = self.on_load_stage if not self.ui_load_stage_pressed else self.on_close
                
                self.ui_load_stage_ref = datadoo_ui_utils.ui_button_builder(label=label,
                    name=name,
                    tooltip=tooltip,
                    on_clicked_fn=on_clicked)
                if self.ui_load_stage_pressed:
                    self.ui_select_paths_ref = datadoo_ui_utils.ui_button_builder(label="Select path ",
                        name="SELECT PATHS",
                        tooltip="Press for selecting paths randoms",
                        on_clicked_fn=self.on_set_paths_physics)
                    
                    auto_drive_name = "AUTOMATIC" if self.cosmos_cookoff._auto_drive else "MANUAL"
                    self.ui_auto_drive_ref = datadoo_ui_utils.ui_button_builder(label="Auto drive mode ",
                        name=auto_drive_name,
                        tooltip="Set the auto drive mode",
                        on_clicked_fn=self.on_auto_drive_set)
                    
                    self.ui_use_cosmos_ref = datadoo_ui_utils.ui_checkbox_field_builder(label="Use Cosmos ",
                    name="use_cosmos",
                    default_val=self.ui_use_cosmos_selected,
                    tooltip="Use Cosmos for selecting the correct path",
                    on_changed_fn=self.on_use_cosmos)
                    
                    if not self.ui_use_cosmos_selected:
                        self.ui_path_list_ref = datadoo_ui_utils.ui_combobox_builder(label="Paths ",
                            name="paths_list",
                            tooltip="Select the path to follow without Cosmos",
                            on_changed_fn=self.on_selected_drive_path,
                            options=["PATH LEFT", "PATH RIGHT"])

    def on_load_stage(self, *args):
        loading_stage = omni.kit.async_engine.run_coroutine(self.cosmos_cookoff.load_cosmos_stage())
        self.ui_load_stage_pressed = True
        self.build_cosmos_cookoff_buttons()

    def on_close(self, *args):
        closing_stage = omni.kit.async_engine.run_coroutine(self.cosmos_cookoff.close_cosmos_stage())
        self.ui_load_stage_pressed = False
        self.build_cosmos_cookoff_buttons()

    def on_set_paths_physics(self, *args):
        self.cosmos_cookoff.set_paths_physics()

    def on_auto_drive_set(self, *args):
        self.cosmos_cookoff.set_auto_drive(not self.cosmos_cookoff._auto_drive)
        self.build_cosmos_cookoff_buttons()

    def on_selected_drive_path(self, *args):
        index = self.ui_path_list_ref.model.get_item_value_model().get_value_as_int()
        self.cosmos_cookoff.set_drive_path(index)

    def on_use_cosmos(self, *args):
        use_cosmos = self.ui_use_cosmos_ref.model.get_value_as_bool()
        self.ui_use_cosmos_selected = use_cosmos
        self.cosmos_cookoff.set_use_cosmos(use_cosmos)
        self.build_cosmos_cookoff_buttons()
   