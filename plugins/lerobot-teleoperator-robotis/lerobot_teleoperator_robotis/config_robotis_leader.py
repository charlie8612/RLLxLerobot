from dataclasses import dataclass, field

from lerobot.teleoperators.config import TeleoperatorConfig


@dataclass
class RobotisLeaderBaseConfig:
    """Base configuration for ROBOTIS OMY-L100 leader arm (not registered with draccus).

    Reads joint positions from OMY-L100 X-series Dynamixel motors
    (XH540-W150, XC330-T288, XC330-T181) via dynamixel_sdk, maps them
    to Piper follower joint space using the same absolute mapping as
    the working ROS2 robotis2piper.py node.
    """

    port: str = "/dev/robotis_left"
    baudrate: int = 4_000_000
    protocol_version: float = 2.0

    # Dynamixel motor IDs on the OMY-L100 (joints 1-6 + gripper)
    motor_ids: list[int] = field(default_factory=lambda: [1, 2, 3, 4, 5, 6, 7])

    # X-series position resolution: 4096 units = 1 revolution (2π rad)
    units_per_revolution: int = 4096

    # X-series zero-radian position (center of 0-4095 range)
    position_zero_offset: int = 2048

    # Joint mapping: (leader_index, scale, offset_rad, piper_min_deg, piper_max_deg)
    #   piper_rad = scale * leader_rad + offset → then convert to degrees
    #
    # ROS2 robotis2piper.py 的 mapping（base↔tip 反轉配置，與當前物理擺放不同）:
    #   Piper J1 = M4 * 1.0  + 0.0    | Piper J4 = M2 * 1.0  - 1.57
    #   Piper J2 = M6 * 1.0  + 1.57   | Piper J5 = M3 * 1.0  + 1.57
    #   Piper J3 = M5 * 1.0  - 2.66   | Piper J6 = M1 * -1.0 + 0.33
    #
    # 當前物理擺放（同向配置，calibrate_mapping.py 實測）的 motor→joint 對應:
    #   M1→J1, M2→J2, M3→J3, M5→J4, M4→J5, M6→J6
    #
    # 對應關係轉換：ROS2 的 offset 搭配當前的 motor→joint 對應
    #   ROS2: J1←M4(+1.0, +0.0)   → 當前 M1→J1: 同為 base rotation, scale=+1.0, offset=+0.0
    #   ROS2: J2←M6(+1.0, +1.57)  → 當前 M2→J2: 同為 shoulder,      scale=+1.0, offset=+1.57
    #   ROS2: J3←M5(+1.0, -2.66)  → 當前 M3→J3: 同為 elbow,         scale=+1.0, offset=-2.66
    #   ROS2: J4←M2(+1.0, -1.57)  → 當前 M5→J4: 同為 wrist roll,    scale=+1.0, offset=-1.57
    #   ROS2: J5←M3(+1.0, +1.57)  → 當前 M4→J5: 同為 wrist pitch,   scale=+1.0, offset=+1.57
    #   ROS2: J6←M1(-1.0, +0.33)  → 當前 M6→J6: 同為 wrist rotation, scale=-1.0, offset=+0.33
    #
    # --- OLD calibration (calibrate_mapping.py, scale 有偏差) ---
    # (0, +0.9998, +0.000000, -150.0, 150.0),  # Piper J1 ← M1
    # (1, +0.8016, +1.243209, 0.0, 150.0),     # Piper J2 ← M2
    # (2, +1.2903, -3.408457, -170.0, 0.0),     # Piper J3 ← M3
    # (4, +0.9985, -1.595226, -100.0, 100.0),   # Piper J4 ← M5
    # (3, +0.9993, +1.117492, -70.0, 70.0),     # Piper J5 ← M4
    # (5, -1.0010, -0.001535, -120.0, 120.0),   # Piper J6 ← M6
    # --- END OLD ---
    joint_mapping: list[tuple] = field(default_factory=lambda: [
        (0, +1.0, +0.00,  -150.0, 150.0),  # Piper J1 ← M1  (base rotation)
        (1, +1.0, +1.57,     0.0, 150.0),  # Piper J2 ← M2  (shoulder)
        (2, +1.0, -2.66,  -170.0,   0.0),  # Piper J3 ← M3  (elbow)
        (4, +1.0, -1.57,  -100.0, 100.0),  # Piper J4 ← M5  (wrist roll)
        (3, +1.0, +1.57,   -70.0,  70.0),  # Piper J5 ← M4  (wrist pitch)
        (5, -1.0, +0.33,  -120.0, 120.0),  # Piper J6 ← M6  (wrist rotation)
    ])

    # Gripper mapping
    # OLD: gripper_piper_open_mm = 35.0 (ROS2 原始值，只用了一半行程)
    gripper_leader_index: int = 6
    gripper_leader_closed_rad: float = -0.8
    gripper_leader_open_rad: float = 0.0
    gripper_piper_closed_mm: float = 0.0
    gripper_piper_open_mm: float = 70.0  # Piper 硬體最大值 (GRIPPER_RANGE_MM)

    # Smoothing: 0.0 = no smoothing, 0.9 = very smooth (more lag)
    smoothing_factor: float = 0.0

    # Gripper spring effect (same as ROS2 spring_actuator_controller on rh_r1_joint)
    # Applies torque = -stiffness * (position - neutral) - damping * velocity
    # to make the leader gripper auto-return to open position.
    gripper_spring_enabled: bool = True
    gripper_spring_stiffness: float = 0.06       # N·m/rad (ROS2 default)
    gripper_spring_neutral_rad: float = 0.0       # open position
    gripper_spring_damping: float = 0.004         # N·m·s/rad (ROS2 default)
    gripper_spring_max_current: int = 150         # max Goal Current units (safety clamp)


@TeleoperatorConfig.register_subclass("robotis_leader")
@dataclass
class RobotisLeaderConfig(TeleoperatorConfig, RobotisLeaderBaseConfig):
    """Configuration for ROBOTIS OMY-L100 leader arm teleoperator."""
    pass
