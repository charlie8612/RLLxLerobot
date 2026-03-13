from dataclasses import dataclass, field

from lerobot.teleoperators.config import TeleoperatorConfig


@TeleoperatorConfig.register_subclass("keypad_joint")
@dataclass
class KeypadJointConfig(TeleoperatorConfig):
    """Configuration for keyboard joint-space teleoperator.

    Controls individual joints using keyboard keys.

    Keys:
        1-6     : Select joint 1~6
        7       : Select gripper
        Up/Down : Increase/decrease selected joint angle
        +/-     : Increase/decrease step size
        r       : Reset all joints to initial position
        0       : Move to zero position (home)
    """

    # Step size for joint adjustment (degrees per key press)
    joint_step: float = 1.0

    # Step size for gripper adjustment (mm per key press)
    gripper_step: float = 2.0

    # Number of arm joints (excluding gripper)
    num_joints: int = 6

    # Whether gripper is attached
    gripper_exist: bool = True

    # Joint names (must match robot features)
    joint_names: list[str] = field(
        default_factory=lambda: [
            "joint_1", "joint_2", "joint_3",
            "joint_4", "joint_5", "joint_6",
        ]
    )

    # Initial positions (degrees for joints, mm for gripper) - home position
    initial_positions: list[float] = field(
        default_factory=lambda: [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    )
