# SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

import omni.ui as ui

LABEL_WIDTH = 128
FIELD_HEIGHT = 32
HORIZONTAL_SPACING = 4

class BaseRef():
    def __init__(self):
        self.model: ui.AbstractValueModel = None
        self.id = None
    
    def update(self):
        if self.model:
            self.id = id(self.model)

class CheckBoxFieldRef(BaseRef):
    def __init__(self):
        super().__init__()
        self.label: ui.Label = None
        self.checkbox_field: ui.CheckBox = None

class ButtonRef(BaseRef):
    def __init__(self):
        super().__init__()
        self.label: ui.Label = None
        self.button: ui.Button = None

class ComboboxRef(BaseRef):
    def __init__(self):
        super().__init__()
        self.label: ui.Label = None
        self.options: ui.ComboBox = None
        self.button: ui.Button = None

def ui_checkbox_field_builder(label: str ="", name: str = "CheckboxField", default_val: int =1, tooltip: str ="", 
    on_changed_fn=None) -> CheckBoxFieldRef:
    checkbox_field_ref = CheckBoxFieldRef()
    with ui.HStack():
        checkbox_field_ref.label = ui.Label(label, width=LABEL_WIDTH, alignment=ui.Alignment.LEFT_CENTER, tooltip=tooltip)
        checkbox_field_ref.checkbox_field = ui.CheckBox(name=name, width=ui.Fraction(1), height=FIELD_HEIGHT, 
            alignment=ui.Alignment.LEFT_CENTER)
        checkbox_field_ref.model = checkbox_field_ref.checkbox_field.model
        checkbox_field_ref.model.set_value(default_val)
        checkbox_field_ref.model.add_value_changed_fn(on_changed_fn)

        checkbox_field_ref.update()
        
    return checkbox_field_ref

def ui_button_builder(label: str ="", name: str = "Button", tooltip: str ="", on_clicked_fn=None) -> ButtonRef:
    button_ref = ButtonRef()
    with ui.HStack():
        button_ref.label = ui.Label(label, width=LABEL_WIDTH, alignment=ui.Alignment.LEFT_CENTER, tooltip=tooltip)
        button_ref.button = ui.Button(name, height=FIELD_HEIGHT, clicked_fn=on_clicked_fn)

    return button_ref

def ui_combobox_builder(label: str ="", name: str = "ComboboxField", tooltip: str ="", 
    on_changed_fn=None, options: list = []) -> ComboboxRef:
    combobox_ref = ComboboxRef()
    with ui.HStack():
        combobox_ref.label = ui.Label(label, width=LABEL_WIDTH, alignment=ui.Alignment.LEFT_CENTER, tooltip=tooltip)
        combobox_ref.options = ui.ComboBox(0, *options, name=name)
        combobox_ref.model = combobox_ref.options.model
        combobox_ref.options.model.add_item_changed_fn(on_changed_fn)
        combobox_ref.update()
        
    return combobox_ref