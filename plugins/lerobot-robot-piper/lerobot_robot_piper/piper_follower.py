import logging
import time
from functools import cached_property

import numpy as np

from lerobot.cameras.utils import make_cameras_from_configs
from lerobot.processor import RobotAction, RobotObservation
from lerobot.robots.robot import Robot
from lerobot.utils.decorators import check_if_already_connected, check_if_not_connected

from .config_piper_follower import PiperFollowerConfig

logger = logging.getLogger(__name__)

# Piper joint limits in degrees
JOINT_LIMITS_DEG = {
    "joint_1": (-150.0, 150.0),
    "joint_2": (0.0, 180.0),
    "joint_3": (-170.0, 0.0),
    "joint_4": (-100.0, 100.0),
    "joint_5": (-70.0, 70.0),
    "joint_6": (-120.0, 120.0),
}
GRIPPER_RANGE_MM = (0.0, 70.0)

JOINT_NAMES = ["joint_1", "joint_2", "joint_3", "joint_4", "joint_5", "joint_6"]


class PiperFollower(Robot):
    """LeRobot-compatible driver for AgileX Piper robot arm.

    Units at API level:
      - Joint positions: degrees
      - Gripper position: mm (stroke)

    The piper_sdk uses 0.001 degree and 0.001 mm internally.
    """

    config_class = PiperFollowerConfig
    name = "piper_follower"

    def __init__(self, config: PiperFollowerConfig):
        super().__init__(config)
        self.config = config
        self.piper = None
        self._is_connected = False
        self.cameras = make_cameras_from_configs(config.cameras)

    @cached_property
    def observation_features(self) -> dict[str, type | tuple]:
        features: dict[str, type | tuple] = {
            f"{name}.pos": float for name in JOINT_NAMES
        }
        features["gripper.pos"] = float
        for cam_name in self.cameras:
            cam_cfg = self.config.cameras[cam_name]
            features[cam_name] = (cam_cfg.height, cam_cfg.width, 3)
        return features

    @cached_property
    def action_features(self) -> dict[str, type]:
        features: dict[str, type] = {f"{name}.pos": float for name in JOINT_NAMES}
        features["gripper.pos"] = float
        return features

    @property
    def is_connected(self) -> bool:
        return self._is_connected and all(
            cam.is_connected for cam in self.cameras.values()
        )

    @property
    def is_calibrated(self) -> bool:
        return True

    @check_if_already_connected
    def connect(self, calibrate: bool = True) -> None:
        from piper_sdk import C_PiperInterface_V2

        self.piper = C_PiperInterface_V2(self.config.can_port)
        self.piper.ConnectPort()

        # Enable all motors using EnablePiper (blocks until confirmed)
        logger.info("Enabling Piper arm...")
        enable_attempts = 0
        while not self.piper.EnablePiper():
            time.sleep(0.01)
            enable_attempts += 1
            if enable_attempts > 500:
                raise RuntimeError("Failed to enable Piper arm after 5 seconds")
        logger.info("Piper arm enabled.")

        # Prevent startup rush: the arm controller remembers the last
        # JointCtrl target from the previous session. If we enable MOVE_J
        # at full speed, it rushes to that old position.
        # Fix: enable at minimum speed, immediately send hold-in-place to
        # overwrite the stale target, then ramp up to normal speed.
        joint_msgs = self.piper.GetArmJointMsgs()
        js = joint_msgs.joint_state

        # Start MOVE_J at 1% speed — even if the stale target fires, movement is minimal
        self.piper.MotionCtrl_2(0x01, 0x01, 1, 0xAD)

        # Immediately overwrite stale target with current position (send multiple
        # times to ensure at least one is processed before the stale command)
        for _ in range(5):
            self.piper.JointCtrl(js.joint_1, js.joint_2, js.joint_3,
                                 js.joint_4, js.joint_5, js.joint_6)
        time.sleep(0.1)

        # Now safe to switch to normal speed
        self.piper.MotionCtrl_2(0x01, 0x01, self.config.speed_rate, 0xAD)

        # Enable gripper
        gripper_msgs = self.piper.GetArmGripperMsgs()
        current_grip = abs(gripper_msgs.gripper_state.grippers_angle)
        self.piper.GripperCtrl(current_grip, self.config.gripper_effort, 0x01, 0)

        for cam in self.cameras.values():
            cam.connect()

        self._is_connected = True
        logger.info("PiperFollower connected on %s", self.config.can_port)

    def calibrate(self) -> None:
        pass

    def configure(self) -> None:
        pass

    @check_if_not_connected
    def get_observation(self) -> RobotObservation:
        joint_msgs = self.piper.GetArmJointMsgs()
        gripper_msgs = self.piper.GetArmGripperMsgs()

        js = joint_msgs.joint_state
        obs: RobotObservation = {
            "joint_1.pos": js.joint_1 / 1000.0,
            "joint_2.pos": js.joint_2 / 1000.0,
            "joint_3.pos": js.joint_3 / 1000.0,
            "joint_4.pos": js.joint_4 / 1000.0,
            "joint_5.pos": js.joint_5 / 1000.0,
            "joint_6.pos": js.joint_6 / 1000.0,
            "gripper.pos": gripper_msgs.gripper_state.grippers_angle / 1000.0,
        }

        for cam_key, cam in self.cameras.items():
            obs[cam_key] = cam.read_latest()

        return obs

    @check_if_not_connected
    def send_action(self, action: RobotAction) -> RobotAction:
        goal = {key.removesuffix(".pos"): val for key, val in action.items() if key.endswith(".pos")}

        # Clamp to joint limits
        for name, (lo, hi) in JOINT_LIMITS_DEG.items():
            if name in goal:
                goal[name] = float(np.clip(goal[name], lo, hi))
        if "gripper" in goal:
            goal["gripper"] = float(np.clip(goal["gripper"], *GRIPPER_RANGE_MM))

        # Safety: limit relative movement per step
        if self.config.max_relative_target is not None:
            current_obs = self.get_observation()
            max_delta = self.config.max_relative_target
            for name in JOINT_NAMES:
                key = f"{name}.pos"
                if name in goal and key in current_obs:
                    current = current_obs[key]
                    diff = goal[name] - current
                    clamped_diff = float(np.clip(diff, -max_delta, max_delta))
                    goal[name] = current + clamped_diff
            if "gripper" in goal and "gripper.pos" in current_obs:
                g_diff = goal["gripper"] - current_obs["gripper.pos"]
                g_diff = float(np.clip(g_diff, -max_delta, max_delta))
                goal["gripper"] = current_obs["gripper.pos"] + g_diff

        # Convert degrees to 0.001 degree (int) for SDK
        j = [int(round(goal.get(name, 0.0) * 1000)) for name in JOINT_NAMES]

        self.piper.MotionCtrl_2(0x01, 0x01, self.config.speed_rate, 0xAD)
        self.piper.JointCtrl(j[0], j[1], j[2], j[3], j[4], j[5])

        # Gripper: convert mm to 0.001 mm
        gripper_val = int(round(goal.get("gripper", 0.0) * 1000))
        self.piper.GripperCtrl(abs(gripper_val), self.config.gripper_effort, 0x01, 0)

        return {f"{name}.pos": goal.get(name, 0.0) for name in JOINT_NAMES + ["gripper"]}

    @check_if_not_connected
    def disconnect(self) -> None:
        # Move to rest position before disabling to prevent the arm from dropping
        self._move_to_rest()

        if self.piper is not None:
            self.piper.DisableArm()
            self.piper.GripperCtrl(0, 0, 0x00, 0)
        for cam in self.cameras.values():
            cam.disconnect()
        self._is_connected = False
        logger.info("PiperFollower disconnected.")

    # Rest position: arm folded, safe for power-off
    REST_STATE = {
        "joint_1.pos": -0.83,
        "joint_2.pos": -0.14,
        "joint_3.pos": -0.38,
        "joint_4.pos": -1.39,
        "joint_5.pos": 0.0,
        "joint_6.pos": 2.11,
        "gripper.pos": 0.0,
    }
    _SAFE_SPEED = 30.0      # deg/s
    _CONTROL_RATE = 100.0   # Hz
    _MIN_DURATION = 0.3     # seconds

    def _move_to_rest(self) -> None:
        """Smoothstep interpolation to rest position before disconnect."""
        logger.info("Moving to rest position...")
        try:
            obs = self.get_observation()
            keys = [f"{n}.pos" for n in JOINT_NAMES] + ["gripper.pos"]
            current = {k: obs[k] for k in keys}

            max_delta = max(abs(self.REST_STATE[k] - current[k]) for k in keys)
            duration = max(max_delta / self._SAFE_SPEED, self._MIN_DURATION)

            steps = max(int(duration * self._CONTROL_RATE), 1)
            dt = 1.0 / self._CONTROL_RATE
            for i in range(steps):
                t = (i + 1) / steps
                t = t * t * (3 - 2 * t)  # smoothstep
                action = {k: current[k] + t * (self.REST_STATE[k] - current[k]) for k in keys}
                self.send_action(action)
                time.sleep(dt)
            logger.info("Rest position reached.")
        except Exception as e:
            logger.warning("Failed to reach rest position: %s", e)
