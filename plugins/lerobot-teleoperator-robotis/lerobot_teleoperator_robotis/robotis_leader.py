import logging
import math
import struct
from typing import Any

from dynamixel_sdk import GroupSyncRead, PacketHandler, PortHandler

from lerobot.processor import RobotAction
from lerobot.teleoperators.teleoperator import Teleoperator

from .config_robotis_leader import RobotisLeaderConfig

logger = logging.getLogger(__name__)

# X-series Dynamixel control table (XH540-W150, XC330-T288, XC330-T181)
ADDR_TORQUE_ENABLE = 64
ADDR_GOAL_CURRENT = 102
LEN_GOAL_CURRENT = 2
ADDR_PRESENT_POSITION = 132
LEN_PRESENT_POSITION = 4
ADDR_PRESENT_VELOCITY = 128
LEN_PRESENT_VELOCITY = 4

RAD_TO_DEG = 180.0 / math.pi

# XC330-T181 current unit: ~0.671 mA per unit (from model file)
XC330_T181_CURRENT_UNIT = 0.0006709470296015791  # N·m per Goal Current unit


class RobotisLeader(Teleoperator):
    """ROBOTIS OMY-L100 leader arm teleoperator.

    Reads joint positions from X-series Dynamixel motors (XH540, XC330)
    via dynamixel_sdk Protocol 2.0 sync_read, then maps them to Piper
    follower joint space.

    Uses the same absolute mapping as the ROS2 robotis2piper.py node:
      piper_rad = scale * leader_rad + offset
    Then converts to degrees for PiperFollower.
    """

    config_class = RobotisLeaderConfig
    name = "robotis_leader"

    def __init__(self, config: RobotisLeaderConfig):
        super().__init__(config)
        self.config = config
        self._is_connected = False
        self._port_handler: PortHandler | None = None
        self._packet_handler: PacketHandler | None = None
        self._sync_reader: GroupSyncRead | None = None
        self._prev_rad: list[float] | None = None

        self._joint_names = [
            "joint_1", "joint_2", "joint_3",
            "joint_4", "joint_5", "joint_6",
            "gripper",
        ]

    # ---- Properties ----

    @property
    def action_features(self) -> dict[str, type]:
        return {f"{name}.pos": float for name in self._joint_names}

    @property
    def feedback_features(self) -> dict[str, type]:
        return {}

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    @property
    def is_calibrated(self) -> bool:
        return True

    # ---- Lifecycle ----

    def connect(self, calibrate: bool = True) -> None:
        if self._is_connected:
            raise RuntimeError("RobotisLeader is already connected.")

        port = PortHandler(self.config.port)
        if not port.openPort():
            raise ConnectionError(f"Failed to open port {self.config.port}")
        if not port.setBaudRate(self.config.baudrate):
            port.closePort()
            raise ConnectionError(f"Failed to set baud rate {self.config.baudrate}")

        packet = PacketHandler(self.config.protocol_version)
        self._port_handler = port
        self._packet_handler = packet

        # Disable torque on all motors so the arm can be moved freely
        for mid in self.config.motor_ids:
            result, error = packet.write1ByteTxRx(port, mid, ADDR_TORQUE_ENABLE, 0)
            if result != 0:
                logger.warning(f"Motor {mid} torque disable failed: {packet.getTxRxResult(result)}")

        # Enable gripper spring effect: enable torque on gripper motor only
        # Motor is already in Current Control Mode (Operating Mode = 0), so
        # enabling torque lets us write Goal Current for the spring force.
        gripper_mid = self.config.motor_ids[self.config.gripper_leader_index]
        if self.config.gripper_spring_enabled:
            result, error = packet.write1ByteTxRx(port, gripper_mid, ADDR_TORQUE_ENABLE, 1)
            if result != 0:
                logger.warning(f"Gripper motor {gripper_mid} torque enable failed")
            else:
                logger.info(f"Gripper spring enabled on M{gripper_mid}")

        # Setup sync reader for Present_Position
        reader = GroupSyncRead(port, packet, ADDR_PRESENT_POSITION, LEN_PRESENT_POSITION)
        for mid in self.config.motor_ids:
            if not reader.addParam(mid):
                raise RuntimeError(f"Failed to add motor {mid} to sync reader")
        self._sync_reader = reader

        # Verify read and show initial state
        leader_rad = self._read_positions_rad()
        mapped = self._map_to_piper(leader_rad)
        logger.info(
            f"RobotisLeader connected on {self.config.port} @ {self.config.baudrate} bps, "
            f"{len(self.config.motor_ids)} motors"
        )
        logger.info(f"  Leader (rad): {[f'{v:+.4f}' for v in leader_rad]}")
        logger.info(f"  Piper target: {{{', '.join(f'{k}: {v:.1f}' for k, v in mapped.items())}}}")

        self._is_connected = True

    def calibrate(self) -> None:
        pass

    def configure(self) -> None:
        pass

    def get_action(self) -> RobotAction:
        """Read leader positions and map to Piper joint space (absolute)."""
        leader_rad = self._read_positions_rad()
        if self.config.gripper_spring_enabled:
            self._apply_gripper_spring(leader_rad)
        return self._map_to_piper(leader_rad)

    def send_feedback(self, feedback: dict[str, Any]) -> None:
        pass

    def disconnect(self) -> None:
        # Disable gripper torque before closing
        if self._port_handler is not None and self._packet_handler is not None:
            gripper_mid = self.config.motor_ids[self.config.gripper_leader_index]
            self._packet_handler.write1ByteTxRx(
                self._port_handler, gripper_mid, ADDR_TORQUE_ENABLE, 0
            )
        if self._sync_reader is not None:
            self._sync_reader.clearParam()
            self._sync_reader = None
        if self._port_handler is not None:
            self._port_handler.closePort()
            self._port_handler = None
        self._packet_handler = None
        self._is_connected = False
        logger.info("RobotisLeader disconnected.")

    # ---- Internal ----

    def _apply_gripper_spring(self, leader_rad: list[float]) -> None:
        """Apply spring torque to gripper motor (same as ROS2 spring_actuator_controller).

        torque = -stiffness * (position - neutral) - damping * velocity
        Then convert to Goal Current units and write to motor.
        """
        grip_idx = self.config.gripper_leader_index
        grip_mid = self.config.motor_ids[grip_idx]
        grip_pos = leader_rad[grip_idx]

        # Read velocity for damping
        raw_vel, res, err = self._packet_handler.read4ByteTxRx(
            self._port_handler, grip_mid, ADDR_PRESENT_VELOCITY
        )
        if res == 0 and err == 0:
            signed_vel = struct.unpack("i", struct.pack("I", raw_vel))[0]
            # X-series velocity unit: 0.0239691227 rev/min → convert to rad/s
            grip_vel = signed_vel * 0.0239691227 * 2.0 * math.pi / 60.0
        else:
            grip_vel = 0.0

        # Spring + damping torque
        torque = (
            -self.config.gripper_spring_stiffness * (grip_pos - self.config.gripper_spring_neutral_rad)
            - self.config.gripper_spring_damping * grip_vel
        )

        # Convert torque to Goal Current units
        current_raw = int(torque / XC330_T181_CURRENT_UNIT)

        # Safety clamp
        max_cur = self.config.gripper_spring_max_current
        current_raw = max(-max_cur, min(current_raw, max_cur))

        # Write Goal Current (signed 16-bit, pack as unsigned for SDK)
        value = current_raw & 0xFFFF
        self._packet_handler.write2ByteTxRx(
            self._port_handler, grip_mid, ADDR_GOAL_CURRENT, value
        )

    def _map_to_piper(self, leader_rad: list[float]) -> RobotAction:
        """Same mapping as robotis2piper.py: piper_rad = scale * leader + offset → degrees."""
        action: RobotAction = {}

        for j, (leader_idx, scale, offset_rad, min_deg, max_deg) in enumerate(self.config.joint_mapping):
            val_rad = scale * leader_rad[leader_idx] + offset_rad
            val_deg = val_rad * RAD_TO_DEG
            val_deg = max(min_deg, min(val_deg, max_deg))
            action[f"{self._joint_names[j]}.pos"] = val_deg

        # Gripper: linear scale from leader rad range → Piper mm range
        grip_rad = leader_rad[self.config.gripper_leader_index]
        grip_range_rad = self.config.gripper_leader_open_rad - self.config.gripper_leader_closed_rad
        grip_range_mm = self.config.gripper_piper_open_mm - self.config.gripper_piper_closed_mm
        grip_ratio = (grip_rad - self.config.gripper_leader_closed_rad) / grip_range_rad
        grip_mm = self.config.gripper_piper_closed_mm + grip_ratio * grip_range_mm
        grip_mm = max(self.config.gripper_piper_closed_mm, min(grip_mm, self.config.gripper_piper_open_mm))
        action["gripper.pos"] = grip_mm

        return action

    def _read_positions_rad(self) -> list[float]:
        """Sync read Present_Position from all motors, return as radians.

        Retries up to 3 times on transient communication errors (e.g. USB-Serial glitch).
        Falls back to previous reading if all retries fail.
        """
        max_retries = 3
        for attempt in range(max_retries):
            result = self._sync_reader.txRxPacket()
            if result == 0:
                break
            if attempt < max_retries - 1:
                logger.warning(
                    f"Sync read attempt {attempt + 1}/{max_retries} failed: "
                    f"{self._packet_handler.getTxRxResult(result)}, retrying..."
                )
            else:
                if self._prev_rad is not None:
                    logger.warning(
                        f"Sync read failed after {max_retries} attempts, using previous reading"
                    )
                    return list(self._prev_rad)
                raise RuntimeError(
                    f"Sync read failed after {max_retries} attempts (no previous reading): "
                    f"{self._packet_handler.getTxRxResult(result)}"
                )

        positions = []
        for mid in self.config.motor_ids:
            if not self._sync_reader.isAvailable(mid, ADDR_PRESENT_POSITION, LEN_PRESENT_POSITION):
                if self._prev_rad is not None:
                    logger.warning(f"Motor {mid} data not available, using previous reading")
                    return list(self._prev_rad)
                raise RuntimeError(f"Motor {mid} data not available (no previous reading)")
            raw = self._sync_reader.getData(mid, ADDR_PRESENT_POSITION, LEN_PRESENT_POSITION)
            signed = struct.unpack("i", struct.pack("I", raw))[0]
            centered = signed - self.config.position_zero_offset
            rad = centered * 2.0 * math.pi / self.config.units_per_revolution
            positions.append(rad)

        # Exponential moving average to reduce jitter
        alpha = self.config.smoothing_factor
        if alpha > 0 and self._prev_rad is not None:
            for i in range(len(positions)):
                positions[i] = alpha * self._prev_rad[i] + (1 - alpha) * positions[i]
        self._prev_rad = list(positions)

        return positions
