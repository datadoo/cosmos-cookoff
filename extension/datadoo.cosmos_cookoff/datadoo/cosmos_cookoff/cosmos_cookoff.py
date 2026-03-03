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
import carb.events
import carb.input
import ctypes
import io
import json
import logging
import numpy
import omni.appwindow
import omni.kit.app
import omni.kit.async_engine
import omni.kit.viewport.utility
import omni.kit.stage_templates
import omni.physx
import omni.timeline
import omni.usd
import os
import requests
import sys
import time

from PIL import Image
from pxr import Usd, UsdShade, Sdf, UsdGeom, Gf, UsdPhysics

class CosmosCookoff():
    # Cosmos Cookoff demo stage
    STAGE_PATH = "https://nvidiacookoff.demo.datadoo.ai/cosmos-cookoff/leatherback_rc.usda"
    
    # Cosmos endpoint URL
    COSMOS_URL = "https://nvidiacookoff.datadoo.net/analyze"

    START_TIME_WAIT = 0.5

    MAX_STEER_ANGLE = 45.0
    MAX_VELOCITY = 2000.0
    STEER_DIF_STEP = 5.0
    VELOCITY_DIF_STEP = 100.0

    def __init__(self) -> None:
        # Logging
        self.logger = logging.getLogger("CosmosCookoff")
        self.logger.addHandler(logging.StreamHandler(sys.stdout))
        self.logger.handlers[0].setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] [%(name)s] %(message)s"))
        self.logger.handlers[0].setLevel(logging.DEBUG)
        
        # Omniverse
        self._usd_conext: omni.usd.UsdContext = None
        self._stage: Usd.Stage = None
        self._omni_app_interface: omni.kit.app.IApp = None
        self._omni_update_stream: carb.events.IEventStream = None
        self._stage_event_stream: carb.events.IEventStream = None
        self._physics_interface = None
        self._timeline: omni.timeline.Timeline = None
        self._app_window: omni.appwindow.IAppWindow = None
        self._keyboard: carb.input.Keyboard = None
        self._input_interface: carb.input.IInput = None

        # Update subscription variables
        self._update_subscription: carb.events.ISubscription = None
        self._physics_subscription: carb.events.ISubscription = None
        self._keyboard_subscription = None
        self._stage_event_subscription: carb.events.ISubscription = None

        # Movement actions
        self.turn_right: bool = False
        self.turn_left: bool = False
        self.move_forward: bool = False
        self.move_backward: bool = False
        self._auto_drive: bool = True

        # Times
        self._current_stage_time: float = 0.0
        self._physics_step: int = 0

        # Request logic
        self._loaded_stage: bool = True
        self._use_cosmos: bool = True
        self._capture_requested: bool = False
        self._camera_captured: bool = False
        self._cosmos_path_requested: bool = False
        self._cosmos_request_task = None
        self._is_path_selected: bool = False

        # Viewport
        self._current_viewport = None
        self._captured_buffer: io.BytesIO = None
        self._leatherback_camera_center_path: str = "/World/leatherback/Rigid_Bodies/Chassis/Camera_Center"

        # Physics
        self._road_prim: list[Usd.Prim] = []
        self._material_rough_prims: list[Usd.Prim] = []
        self._material_slippery_prims: list[Usd.Prim] = []
        self._physic_material_rough_prim: Usd.Prim = None
        self._physic_material_slippery_prim: Usd.Prim = None
        self._visual_material_prims: list[list[Usd.Prim]] = []

        self.leatherback_robot_prim: Usd.Prim = None
        self.leatherback_rigidbody_prim: Usd.Prim = None
        self.steer_right_joint_prim: Usd.Prim = None
        self.steer_left_joint_prim: Usd.Prim = None

        self.wheel_front_right_joint_prim: Usd.Prim = None
        self.wheel_front_left_joint_prim: Usd.Prim = None
        self.wheel_rear_right_joint_prim: Usd.Prim = None
        self.wheel_rear_left_joint_prim: Usd.Prim = None

        self.steer_right_joint_drive_api: UsdPhysics.DriveAPI = None
        self.steer_right_joint_drive_api_pos_attr: Usd.Attribute = None
        self.steer_left_joint_drive_api: UsdPhysics.DriveAPI = None
        self.steer_left_joint_drive_api_pos_attr: Usd.Attribute = None

        self.wheel_front_right_joint_drive_api: UsdPhysics.DriveAPI = None
        self.wheel_front_right_joint_drive_api_pos_attr: Usd.Attribute = None
        self.wheel_front_left_joint_drive_api: UsdPhysics.DriveAPI = None
        self.wheel_front_left_joint_drive_api_pos_attr: Usd.Attribute = None
        self.wheel_rear_right_joint_drive_api: UsdPhysics.DriveAPI = None
        self.wheel_rear_right_joint_drive_api_pos_attr: Usd.Attribute = None
        self.wheel_rear_left_joint_drive_api: UsdPhysics.DriveAPI = None
        self.wheel_rear_left_joint_drive_api_pos_attr: Usd.Attribute = None

        self._steer_angle: float = 0.0
        self._acceleration: float = 0.0

        # Paths
        self._drive_path_selected: int = 0
        self._path_time: float = 0.0
        self._path_left_setup = [
            (0.0, 0.4, False, True, True), 
            (0.4, 0.85, False, False, True),
            (0.85, 1.19, True, False, True),
            (1.19, 4.5, False, False, True),
            (4.5, 5.0, False, False, False)
        ]
        self._path_right_setup = [
            (0.0, 0.4, True, False, True), 
            (0.4, 0.85, False, False, True),
            (0.85, 1.175, False, True, True),
            (1.175, 4.5, False, False, True),
            (4.5, 5.0, False, False, False)
        ]
        self._paths = [self._path_left_setup, self._path_right_setup]

        self._visual_material_paths_slippery = [
            "/World/Looks/Slippery/Frosted_Ice",
            "/World/Looks/Slippery/Mud",
            "/World/Looks/Slippery/Road_Puddles",
            "/World/Looks/Slippery/Grass"
        ]

        self._visual_material_paths_rough = [
            "/World/Looks/Rough/Road_Lanes",
            "/World/Looks/Rough/Asphalt",
            "/World/Looks/Rough/Concrete_Formed",
            "/World/Looks/Rough/Retaining_Block"
        ]

        # Numpy
        self._random_generator: numpy.random.Generator = None

    def setup(self) -> bool:
        # Get current USD context
        self._usd_conext = omni.usd.get_context()
        if self._usd_conext is None:
            self.logger.error("Failed getting USD context")
            return False
        
        # Timeline Interface for checking Play/Pause
        self._timeline = omni.timeline.get_timeline_interface()

        self._omni_app_interface = omni.kit.app.get_app_interface()
        self._omni_update_stream = self._omni_app_interface.get_update_event_stream()

        # Subscribe to App Update
        self._update_subscription = self._omni_update_stream.create_subscription_to_pop(self._on_update, name="on_update")

        # Subscribe to Physics Step (Simulation Logic)
        self._physics_interface = omni.physx.get_physx_interface()
        if self._physics_interface:
            self._physics_subscription = self._physics_interface.subscribe_physics_step_events(self._on_physics_step)

        self._stage_event_stream = self._usd_conext.get_stage_event_stream()
        self._stage_event_subscription = self._stage_event_stream.create_subscription_to_pop(self._on_stage_event)

        self._app_window = omni.appwindow.get_default_app_window()
        self._keyboard = self._app_window.get_keyboard()
        self._input_interface = carb.input.acquire_input_interface()
        self._keyboard_subscription_id = self._input_interface.subscribe_to_keyboard_events(self._keyboard, self._on_keyboard_input)

        current_time = int(time.time())
        self._random_generator = numpy.random.default_rng(current_time)

        return True

    def finish(self):
        self._cleanup_subscriptions()

    async def load_cosmos_stage(self):
        if not self._usd_conext:
            self.logger.error("USD context not set")
            return

        if not self._usd_conext.open_stage(self.STAGE_PATH):
            self.logger.error(f"Cannot open stage {self.STAGE_PATH}")
            return

        self._loaded_stage = False

    async def close_cosmos_stage(self):
        if not self._usd_conext:
            return

        if not self._usd_conext.close_stage():
            self.logger.error("Cannot close stage")
            return
    
        # Create a new stage with the "empty" template and our callback
        stage = omni.kit.stage_templates.new_stage(template="empty")

        self._loaded_stage = True

    def set_paths_physics(self):
        rough_idx = int(self._random_generator.integers(low=0, high=2))
        slippery_idx = 1 if rough_idx == 0 else 0

        physics_material_bind = "material:binding:physics"
        rough_visual_materials_idx = self._random_generator.integers(low=0, high=len(self._material_rough_prims))
        rough_prim = self._road_prim[rough_idx]
        rough_material_prim = self._material_rough_prims[rough_visual_materials_idx]
        rough_binding_api = UsdShade.MaterialBindingAPI(rough_prim)
        rough_binding_api.Bind(rough_material_prim)
        rel = rough_prim.GetRelationship(physics_material_bind)
        if not rel:
            rel = rough_prim.CreateRelationship(physics_material_bind, custom=False)
        rel.SetTargets([Sdf.Path(self._physic_material_rough_prim.GetPath())])

        slippery_visual_materials_idx = self._random_generator.integers(low=0, high=len(self._material_slippery_prims))
        slippery_prim = self._road_prim[slippery_idx]
        slippery_material_prim = self._material_slippery_prims[slippery_visual_materials_idx]
        slippery_binding_api = UsdShade.MaterialBindingAPI(slippery_prim)
        slippery_binding_api.Bind(slippery_material_prim)
        rel = slippery_prim.GetRelationship(physics_material_bind)
        if not rel:
            rel = slippery_prim.CreateRelationship(physics_material_bind, custom=False)
        rel.SetTargets([Sdf.Path(self._physic_material_slippery_prim.GetPath())])

    def set_auto_drive(self, auto_drive: bool):
        self._auto_drive = auto_drive

    def set_drive_path(self, drive_path: int):
        self._drive_path_selected = drive_path

    def set_use_cosmos(self, use_cosmos: bool):
        self._use_cosmos = use_cosmos

    def _reset(self):
        self._current_stage_time = 0.0
        self._path_time = 0.0
        self._is_path_selected = False
        self._steer_angle = 0.0
        self._acceleration = 0.0
        self._capture_requested = False
        self._camera_captured = False
        self._cosmos_path_requested = False

        self.turn_right = False
        self.turn_left = False
        self.move_forward = False

        if self.steer_right_joint_drive_api_pos_attr:
            self.steer_right_joint_drive_api_pos_attr.Set(0.0)
        if self.steer_left_joint_drive_api_pos_attr:
            self.steer_left_joint_drive_api_pos_attr.Set(0.0)
        if self.wheel_front_right_joint_drive_api_pos_attr:
            self.wheel_front_right_joint_drive_api_pos_attr.Set(0.0)
        if self.wheel_front_left_joint_drive_api_pos_attr:
            self.wheel_front_left_joint_drive_api_pos_attr.Set(0.0)
        if self.wheel_rear_right_joint_drive_api_pos_attr:
            self.wheel_rear_right_joint_drive_api_pos_attr.Set(0.0)
        if self.wheel_rear_left_joint_drive_api_pos_attr:
            self.wheel_rear_left_joint_drive_api_pos_attr.Set(0.0)


    def _on_stage_event(self, event):
        if event.type == int(omni.usd.StageEventType.ASSETS_LOADED) and not self._loaded_stage:
            self._loaded_stage = True
            self._stage = self._usd_conext.get_stage()
            if self._stage is None:
                self.logger.error("Stage not opened")
                return
            self._set_physics_prims()

    def _set_physics_prims(self):
        self._road_prim.clear()

        slippery_road_prim = self._stage.GetPrimAtPath("/World/Roads/Snow")
        self._road_prim.append(slippery_road_prim)
        rough_road_prim = self._stage.GetPrimAtPath("/World/Roads/Road")
        self._road_prim.append(rough_road_prim)

        self._material_rough_prims.clear()
        for material_path in self._visual_material_paths_rough:
            material_prim = UsdShade.Material(self._stage.GetPrimAtPath(material_path))
            self._material_rough_prims.append(material_prim)

        self._material_slippery_prims.clear()
        for material_path in self._visual_material_paths_slippery:
            material_prim = UsdShade.Material(self._stage.GetPrimAtPath(material_path))
            self._material_slippery_prims.append(material_prim)

        self._physic_material_rough_prim: Usd.Prim = self._stage.GetPrimAtPath("/World/PhysicsMaterials/RoadMaterial")
        self._physic_material_slippery_prim: Usd.Prim = self._stage.GetPrimAtPath("/World/PhysicsMaterials/SnowMaterial")

        self._visual_material_prims.clear()
        self._visual_material_prims.append(self._material_slippery_prims)
        self._visual_material_prims.append(self._material_rough_prims)
        
        self.leatherback_robot_prim: Usd.Prim = self._stage.GetPrimAtPath("/World/leatherback")
        self.leatherback_rigidbody_prim: Usd.Prim = self._stage.GetPrimAtPath("/World/leatherback/Rigid_Bodies/Chassis")

        self.steer_right_joint_prim: Usd.Prim = self._stage.GetPrimAtPath("/World/leatherback/Joints/Knuckle__Upright__Front_Right")
        self.steer_left_joint_prim: Usd.Prim = self._stage.GetPrimAtPath("/World/leatherback/Joints/Knuckle__Upright__Front_Left")

        self.wheel_front_right_joint_prim: Usd.Prim = self._stage.GetPrimAtPath("/World/leatherback/Joints/Wheel__Knuckle__Front_Right")
        self.wheel_front_left_joint_prim: Usd.Prim = self._stage.GetPrimAtPath("/World/leatherback/Joints/Wheel__Knuckle__Front_Left")
        self.wheel_rear_right_joint_prim: Usd.Prim = self._stage.GetPrimAtPath("/World/leatherback/Joints/Wheel__Upright__Rear_Right")
        self.wheel_rear_left_joint_prim: Usd.Prim = self._stage.GetPrimAtPath("/World/leatherback/Joints/Wheel__Upright__Rear_Left")

        self.steer_right_joint_drive_api: UsdPhysics.DriveAPI = UsdPhysics.DriveAPI.Get(self.steer_right_joint_prim, "angular")
        self.steer_right_joint_drive_api_pos_attr: Usd.Attribute = self.steer_right_joint_drive_api.GetTargetPositionAttr()
        self.steer_left_joint_drive_api: UsdPhysics.DriveAPI = UsdPhysics.DriveAPI.Get(self.steer_left_joint_prim, "angular")
        self.steer_left_joint_drive_api_pos_attr: Usd.Attribute = self.steer_left_joint_drive_api.GetTargetPositionAttr()

        self.wheel_front_right_joint_drive_api: UsdPhysics.DriveAPI = UsdPhysics.DriveAPI.Get(self.wheel_front_right_joint_prim, "angular")
        self.wheel_front_right_joint_drive_api_pos_attr: Usd.Attribute = self.wheel_front_right_joint_drive_api.GetTargetVelocityAttr()
        self.wheel_front_left_joint_drive_api: UsdPhysics.DriveAPI = UsdPhysics.DriveAPI.Get(self.wheel_front_left_joint_prim, "angular")
        self.wheel_front_left_joint_drive_api_pos_attr: Usd.Attribute = self.wheel_front_left_joint_drive_api.GetTargetVelocityAttr()
        self.wheel_rear_right_joint_drive_api: UsdPhysics.DriveAPI = UsdPhysics.DriveAPI.Get(self.wheel_rear_right_joint_prim, "angular")
        self.wheel_rear_right_joint_drive_api_pos_attr: Usd.Attribute = self.wheel_rear_right_joint_drive_api.GetTargetVelocityAttr()
        self.wheel_rear_left_joint_drive_api: UsdPhysics.DriveAPI = UsdPhysics.DriveAPI.Get(self.wheel_rear_left_joint_prim, "angular")
        self.wheel_rear_left_joint_drive_api_pos_attr: Usd.Attribute = self.wheel_rear_left_joint_drive_api.GetTargetVelocityAttr()

    def _on_update(self, event: carb.events.IEvent):
        dt = event.payload["dt"]
        if not dt:
            return
        
        # Check if the "Play" button is pressed
        if self._timeline.is_playing():
            self._current_stage_time += dt
            if self._use_cosmos:
                self._on_update_cosmos(self._current_stage_time, dt)
            else:
                self._on_update_without_cosmos(self._current_stage_time, dt)

            if self._auto_drive:
                self._on_update_auto_drive(dt)
            self._on_update_drive(dt)
        elif self._timeline.is_stopped():
            self._reset()
    
    def _on_physics_step(self, dt):
        self._physics_step += 1

    def _on_keyboard_input(self, event: carb.input.KeyboardEvent):
        if self._auto_drive:
            return

        if event.input == carb.input.KeyboardInput.NUMPAD_8:
            if event.type == carb.input.KeyboardEventType.KEY_PRESS or event.type == carb.input.KeyboardEventType.KEY_REPEAT:
                self.move_forward = True
            else:
                self.move_forward = False
        elif event.input == carb.input.KeyboardInput.NUMPAD_2:
            if event.type == carb.input.KeyboardEventType.KEY_PRESS or event.type == carb.input.KeyboardEventType.KEY_REPEAT:
                self.move_backward = True
            else:
                self.move_backward = False

        if event.input == carb.input.KeyboardInput.NUMPAD_6:
            if event.type == carb.input.KeyboardEventType.KEY_PRESS or event.type == carb.input.KeyboardEventType.KEY_REPEAT:
                self.turn_right = True
            else:
                self.turn_right = False
                
        elif event.input == carb.input.KeyboardInput.NUMPAD_4:
            if event.type == carb.input.KeyboardEventType.KEY_PRESS or event.type == carb.input.KeyboardEventType.KEY_REPEAT:
                self.turn_left = True
            else:
                self.turn_left = False

    def _cleanup_subscriptions(self):
        self._update_subscription = None
        self._physics_subscription = None
        self._stage_event_subscription = None
        self._input_interface.unsubscribe_to_keyboard_events(self._keyboard, self._keyboard_subscription_id)

    def _on_update_cosmos(self, current_time: float, delta_time: float):
        if current_time < self.START_TIME_WAIT:
            pass
        elif current_time >= self.START_TIME_WAIT and not self._capture_requested:
            self._capture_camera()
        elif not self._camera_captured:
            pass
        elif self._camera_captured and not self._cosmos_path_requested:
            self._cosmos_path_requested = True
            self._cosmos_request_task = omni.kit.async_engine.run_coroutine(self._check_cosmos_for_path())
        elif not self._is_path_selected:
            pass

    def _on_update_without_cosmos(self, current_time: float, delta_time: float):
        if current_time < self.START_TIME_WAIT:
            pass
        else:
            self._is_path_selected = True
        
    def _capture_camera(self):
        self._current_viewport = omni.kit.viewport.utility.get_active_viewport()

        if not self._current_viewport:
            return
        capture_process = omni.kit.viewport.utility.capture_viewport_to_buffer(self._current_viewport, self._on_capture_completed)
        self._capture_requested = True
    
    def _on_capture_completed(self, buffer, buffer_size, width, height, format, *args):
        try:
            ctypes.pythonapi.PyCapsule_GetPointer.restype = ctypes.POINTER(ctypes.c_byte * buffer_size)
            ctypes.pythonapi.PyCapsule_GetPointer.argtypes = [ctypes.py_object, ctypes.c_char_p]
            content = ctypes.pythonapi.PyCapsule_GetPointer(buffer, None)
        except Exception as e:
            self.logger.error(f"Failed capturing viewport {e}")
            return

        self._captured_buffer = io.BytesIO()
        img = Image.frombuffer('RGBA', (width, height), content.contents).convert('RGB')
        img.save(self._captured_buffer, format='PNG')
        self._captured_buffer.seek(0)
        self._camera_captured = True

    async def _check_cosmos_for_path(self):
        files={"image": ("capture_viewport.png", self._captured_buffer, "image/png")}
        print("Checking with cosmos")
        response = requests.request("POST", self.COSMOS_URL, files=files, timeout=32.0)
        if response.status_code == 200:
            response_content = json.loads(response.content)
            print(response_content)
            self._drive_path_selected = response_content.get("chosen_path")
            if self._drive_path_selected is None:
                self._drive_path_selected = 1
        else:
            print(f"ERROR cosmos response: {response.status_code} {response.content}")
            return
        
        self._is_path_selected = True

    def _on_update_drive(self, dt: float):
        if self.turn_right:
            self._move(-self.STEER_DIF_STEP)
        elif self.turn_left:
            self._move(self.STEER_DIF_STEP)
        else:
            self._no_steer(self.STEER_DIF_STEP)

        if self.move_forward:
            self._accelerate(self.VELOCITY_DIF_STEP)
        elif self.move_backward:
            self._accelerate(-self.VELOCITY_DIF_STEP)
        else:
            self._brake()

    def _accelerate(self, val: float):
        self._acceleration = self._acceleration + val
        self._acceleration = numpy.clip(self._acceleration, -self.MAX_VELOCITY, self.MAX_VELOCITY)

        self.wheel_front_right_joint_drive_api_pos_attr.Set(self._acceleration)
        self.wheel_front_left_joint_drive_api_pos_attr.Set(self._acceleration)
        self.wheel_rear_right_joint_drive_api_pos_attr.Set(self._acceleration)
        self.wheel_rear_left_joint_drive_api_pos_attr.Set(self._acceleration)
        
    def _brake(self):
        self._acceleration = 0.0
        self.wheel_front_right_joint_drive_api_pos_attr.Set(self._acceleration)
        self.wheel_front_left_joint_drive_api_pos_attr.Set(self._acceleration)
        self.wheel_rear_right_joint_drive_api_pos_attr.Set(self._acceleration)
        self.wheel_rear_left_joint_drive_api_pos_attr.Set(self._acceleration)

    def _move(self, val: float):
        self._steer_angle = self._steer_angle + val
        self._steer_angle = numpy.clip(self._steer_angle, -self.MAX_STEER_ANGLE, self.MAX_STEER_ANGLE)

        self.steer_right_joint_drive_api_pos_attr.Set(self._steer_angle)
        self.steer_left_joint_drive_api_pos_attr.Set(self._steer_angle)

    def _no_steer(self, val: float):
        if self._steer_angle == 0.0:
            return
        
        if self._steer_angle > 0.0:
            self._steer_angle = self._steer_angle - val
            self._steer_angle = numpy.clip(self._steer_angle, 0.0, self.MAX_STEER_ANGLE)
        elif self._steer_angle < 0.0:
            self._steer_angle = self._steer_angle + val
            self._steer_angle = numpy.clip(self._steer_angle, -self.MAX_STEER_ANGLE, 0)

        self.steer_right_joint_drive_api_pos_attr.Set(self._steer_angle)
        self.steer_left_joint_drive_api_pos_attr.Set(self._steer_angle)

    def _on_update_auto_drive(self, dt: float):
        if not self._is_path_selected:
            return

        self._path_time = self._path_time + dt

        path = self._paths[self._drive_path_selected]

        current_point = path[-1]
        for point in path:
            if self._path_time >= point[0] and self._path_time < point[1]:
                current_point = point
                break
        
        self.turn_right = current_point[2]
        self.turn_left = current_point[3]
        self.move_forward = current_point[4]
