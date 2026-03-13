"""Run a RobotisLeader in a subprocess to avoid GIL contention."""
import multiprocessing as mp
import logging

logger = logging.getLogger(__name__)


def _leader_worker(config_dict, pipe):
    """Subprocess entry point for RobotisLeader."""
    from .config_robotis_leader import RobotisLeaderConfig
    from .robotis_leader import RobotisLeader

    config = RobotisLeaderConfig(**config_dict)
    leader = RobotisLeader(config)

    try:
        while True:
            msg = pipe.recv()
            cmd = msg[0]

            if cmd == "connect":
                leader.connect(msg[1])
                pipe.send(("ok",))
            elif cmd == "get_action":
                action = leader.get_action()
                pipe.send(("ok", action))
            elif cmd == "disconnect":
                leader.disconnect()
                pipe.send(("ok",))
                break
            elif cmd == "action_features":
                pipe.send(("ok", leader.action_features))
            elif cmd == "is_connected":
                pipe.send(("ok", leader.is_connected))
    except (EOFError, BrokenPipeError):
        try:
            leader.disconnect()
        except Exception:
            pass


class SubprocessLeader:
    """Proxy that runs a RobotisLeader in a separate process."""

    def __init__(self, config):
        self.config = config
        self._parent_pipe, self._child_pipe = mp.Pipe()
        self._process = None
        # Cache features
        from .config_robotis_leader import RobotisLeaderConfig
        from .robotis_leader import RobotisLeader
        temp = RobotisLeader(RobotisLeaderConfig(
            port=config.port,
            baudrate=config.baudrate,
            protocol_version=config.protocol_version,
            motor_ids=config.motor_ids,
            units_per_revolution=config.units_per_revolution,
            position_zero_offset=config.position_zero_offset,
            joint_mapping=config.joint_mapping,
            gripper_leader_index=config.gripper_leader_index,
            gripper_leader_closed_rad=config.gripper_leader_closed_rad,
            gripper_leader_open_rad=config.gripper_leader_open_rad,
            gripper_piper_closed_mm=config.gripper_piper_closed_mm,
            gripper_piper_open_mm=config.gripper_piper_open_mm,
            smoothing_factor=config.smoothing_factor,
            gripper_spring_enabled=config.gripper_spring_enabled,
            gripper_spring_stiffness=config.gripper_spring_stiffness,
            gripper_spring_neutral_rad=config.gripper_spring_neutral_rad,
            gripper_spring_damping=config.gripper_spring_damping,
            gripper_spring_max_current=config.gripper_spring_max_current,
        ))
        self._action_features = temp.action_features

    @property
    def action_features(self):
        return self._action_features

    @property
    def is_connected(self):
        return self._process is not None and self._process.is_alive()

    def connect(self, calibrate=True):
        config_dict = {
            "port": self.config.port,
            "baudrate": self.config.baudrate,
            "protocol_version": self.config.protocol_version,
            "motor_ids": self.config.motor_ids,
            "units_per_revolution": self.config.units_per_revolution,
            "position_zero_offset": self.config.position_zero_offset,
            "joint_mapping": self.config.joint_mapping,
            "gripper_leader_index": self.config.gripper_leader_index,
            "gripper_leader_closed_rad": self.config.gripper_leader_closed_rad,
            "gripper_leader_open_rad": self.config.gripper_leader_open_rad,
            "gripper_piper_closed_mm": self.config.gripper_piper_closed_mm,
            "gripper_piper_open_mm": self.config.gripper_piper_open_mm,
            "smoothing_factor": self.config.smoothing_factor,
            "gripper_spring_enabled": self.config.gripper_spring_enabled,
            "gripper_spring_stiffness": self.config.gripper_spring_stiffness,
            "gripper_spring_neutral_rad": self.config.gripper_spring_neutral_rad,
            "gripper_spring_damping": self.config.gripper_spring_damping,
            "gripper_spring_max_current": self.config.gripper_spring_max_current,
        }
        self._process = mp.Process(
            target=_leader_worker,
            args=(config_dict, self._child_pipe),
            daemon=True,
        )
        self._process.start()
        self._parent_pipe.send(("connect", calibrate))
        resp = self._parent_pipe.recv()
        if resp[0] != "ok":
            raise RuntimeError(f"Subprocess connect failed: {resp}")
        logger.info("SubprocessLeader connected (pid=%d)", self._process.pid)

    def get_action(self):
        self._parent_pipe.send(("get_action",))
        resp = self._parent_pipe.recv()
        return resp[1]

    def disconnect(self):
        if self._process and self._process.is_alive():
            self._parent_pipe.send(("disconnect",))
            try:
                self._parent_pipe.recv()
            except EOFError:
                pass
            self._process.join(timeout=3)
            if self._process.is_alive():
                self._process.terminate()
        logger.info("SubprocessLeader disconnected.")
