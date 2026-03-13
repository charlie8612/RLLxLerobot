from dataclasses import dataclass, field

from lerobot.cameras import CameraConfig
from lerobot.robots.config import RobotConfig


@dataclass
class PiperFollowerBaseConfig:
    """Base configuration for AgileX Piper robot arm (not registered with draccus)."""

    # CAN interface name (e.g., "piper_left", "can0")
    can_port: str = "piper_left"

    # Speed rate percentage for MotionCtrl_2 (0-100)
    speed_rate: int = 50

    # Max relative target per step (degrees). Limits sudden large movements.
    # Set to None to disable safety clamping.
    max_relative_target: float | None = None

    # Gripper default effort in 0.001 N*m (1000 = 1 N*m)
    gripper_effort: int = 1000

    # Cameras (empty by default, add in Phase 3)
    cameras: dict[str, CameraConfig] = field(default_factory=dict)


@RobotConfig.register_subclass("piper_follower")
@dataclass
class PiperFollowerConfig(RobotConfig, PiperFollowerBaseConfig):
    """Configuration for AgileX Piper robot arm as a follower."""
    pass
