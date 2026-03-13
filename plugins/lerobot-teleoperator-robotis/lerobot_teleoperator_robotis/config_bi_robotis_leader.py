from dataclasses import dataclass, field

from lerobot.teleoperators.config import TeleoperatorConfig

from .config_robotis_leader import RobotisLeaderBaseConfig


@TeleoperatorConfig.register_subclass("bi_robotis_leader")
@dataclass
class BiRobotisLeaderConfig(TeleoperatorConfig):
    """Configuration for bimanual (dual) ROBOTIS leader arms."""

    left_arm_config: RobotisLeaderBaseConfig = field(
        default_factory=lambda: RobotisLeaderBaseConfig(port="/dev/robotis_left")
    )
    right_arm_config: RobotisLeaderBaseConfig = field(
        default_factory=lambda: RobotisLeaderBaseConfig(port="/dev/robotis_right")
    )
