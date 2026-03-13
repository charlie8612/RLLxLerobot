import logging
from functools import cached_property
from typing import Any

from lerobot.processor import RobotAction
from lerobot.teleoperators.teleoperator import Teleoperator
from lerobot.utils.decorators import check_if_already_connected, check_if_not_connected

from .config_bi_robotis_leader import BiRobotisLeaderConfig
from .config_robotis_leader import RobotisLeaderConfig
from .robotis_leader import RobotisLeader
from .subprocess_leader import SubprocessLeader

logger = logging.getLogger(__name__)


class BiRobotisLeader(Teleoperator):
    """Bimanual (dual) ROBOTIS leader.

    Left arm runs in the main process. Right arm runs in a subprocess to avoid
    GIL contention from piper_sdk's background CAN receive threads.
    """

    config_class = BiRobotisLeaderConfig
    name = "bi_robotis_leader"

    def __init__(self, config: BiRobotisLeaderConfig):
        super().__init__(config)
        self.config = config

        left_arm_config = RobotisLeaderConfig(
            id=f"{config.id}_left" if config.id else None,
            port=config.left_arm_config.port,
            baudrate=config.left_arm_config.baudrate,
            protocol_version=config.left_arm_config.protocol_version,
            motor_ids=config.left_arm_config.motor_ids,
            units_per_revolution=config.left_arm_config.units_per_revolution,
            position_zero_offset=config.left_arm_config.position_zero_offset,
            joint_mapping=config.left_arm_config.joint_mapping,
            gripper_leader_index=config.left_arm_config.gripper_leader_index,
            gripper_leader_closed_rad=config.left_arm_config.gripper_leader_closed_rad,
            gripper_leader_open_rad=config.left_arm_config.gripper_leader_open_rad,
            gripper_piper_closed_mm=config.left_arm_config.gripper_piper_closed_mm,
            gripper_piper_open_mm=config.left_arm_config.gripper_piper_open_mm,
            smoothing_factor=config.left_arm_config.smoothing_factor,
            gripper_spring_enabled=config.left_arm_config.gripper_spring_enabled,
            gripper_spring_stiffness=config.left_arm_config.gripper_spring_stiffness,
            gripper_spring_neutral_rad=config.left_arm_config.gripper_spring_neutral_rad,
            gripper_spring_damping=config.left_arm_config.gripper_spring_damping,
            gripper_spring_max_current=config.left_arm_config.gripper_spring_max_current,
        )

        self.left_arm = RobotisLeader(left_arm_config)
        self.right_arm = SubprocessLeader(config.right_arm_config)

    @cached_property
    def action_features(self) -> dict[str, type]:
        left_ft = self.left_arm.action_features
        right_ft = self.right_arm.action_features
        return {
            **{f"left_{k}": v for k, v in left_ft.items()},
            **{f"right_{k}": v for k, v in right_ft.items()},
        }

    @cached_property
    def feedback_features(self) -> dict[str, type]:
        return {}

    @property
    def is_connected(self) -> bool:
        return self.left_arm.is_connected and self.right_arm.is_connected

    @property
    def is_calibrated(self) -> bool:
        return True

    @check_if_already_connected
    def connect(self, calibrate: bool = True) -> None:
        self.left_arm.connect(calibrate)
        self.right_arm.connect(calibrate)

    def calibrate(self) -> None:
        pass

    def configure(self) -> None:
        pass

    @check_if_not_connected
    def get_action(self) -> RobotAction:
        left_action = self.left_arm.get_action()
        right_action = self.right_arm.get_action()
        return {
            **{f"left_{k}": v for k, v in left_action.items()},
            **{f"right_{k}": v for k, v in right_action.items()},
        }

    def send_feedback(self, feedback: dict[str, Any]) -> None:
        pass

    @check_if_not_connected
    def disconnect(self) -> None:
        self.left_arm.disconnect()
        self.right_arm.disconnect()
