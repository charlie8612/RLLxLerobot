import logging
import os
import select
import sys
import termios
import threading
import tty
from typing import Any

import numpy as np

from lerobot.processor import RobotAction
from lerobot.teleoperators.teleoperator import Teleoperator
from lerobot.utils.decorators import check_if_already_connected, check_if_not_connected

from .config_keypad_joint import KeypadJointConfig

logger = logging.getLogger(__name__)


class KeypadJoint(Teleoperator):
    """Joint-space keyboard teleoperator using raw terminal input.

    Works over SSH without X11/DISPLAY. Reads keypresses directly from
    the terminal via raw mode.

    Controls:
        1-6     : Select joint 1~6
        7       : Select gripper
        w / Up  : Increase selected joint/gripper
        s / Down: Decrease selected joint/gripper
        +/=     : Increase step size
        -       : Decrease step size
        r       : Reset all to initial position
        0       : Move all to zero (home)
    """

    config_class = KeypadJointConfig
    name = "keypad_joint"

    def __init__(self, config: KeypadJointConfig):
        super().__init__(config)
        self.config = config
        self._is_connected = False

        all_names = list(config.joint_names)
        if config.gripper_exist:
            all_names.append("gripper")
        self._all_names = all_names

        self._positions = np.array(config.initial_positions, dtype=np.float64)
        self._initial = self._positions.copy()
        self._selected = 0
        self._joint_step = config.joint_step
        self._gripper_step = config.gripper_step
        self._lock = threading.Lock()
        self._reader_thread = None
        self._stop_event = threading.Event()
        self._old_term_settings = None

    # ---- Properties ----

    @property
    def action_features(self) -> dict[str, type]:
        return {f"{name}.pos": float for name in self._all_names}

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

    @check_if_already_connected
    def connect(self, calibrate: bool = True) -> None:
        # Save terminal settings and switch to raw mode
        self._old_term_settings = termios.tcgetattr(sys.stdin)
        tty.setcbreak(sys.stdin.fileno())

        self._stop_event.clear()
        self._reader_thread = threading.Thread(target=self._read_keys, daemon=True)
        self._reader_thread.start()
        self._is_connected = True
        self._print_status()
        logger.info("KeypadJoint connected (terminal raw mode). Keys: 1-7 select, Up/Down adjust.")

    def calibrate(self) -> None:
        pass

    def configure(self) -> None:
        pass

    @check_if_not_connected
    def disconnect(self) -> None:
        self._stop_event.set()
        if self._reader_thread is not None:
            self._reader_thread.join(timeout=1.0)
        # Restore terminal settings
        if self._old_term_settings is not None:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self._old_term_settings)
            self._old_term_settings = None
        self._is_connected = False
        print()  # newline after status line
        logger.info("KeypadJoint disconnected.")

    # ---- Core ----

    @check_if_not_connected
    def get_action(self) -> RobotAction:
        with self._lock:
            return {
                f"{name}.pos": float(self._positions[i])
                for i, name in enumerate(self._all_names)
            }

    def send_feedback(self, feedback: dict[str, Any]) -> None:
        pass

    # ---- Terminal key reading ----

    def _read_keys(self):
        """Background thread: read raw keypresses from stdin using os.read (unbuffered)."""
        fd = sys.stdin.fileno()
        while not self._stop_event.is_set():
            ready, _, _ = select.select([fd], [], [], 0.05)
            if not ready:
                continue
            try:
                data = os.read(fd, 16)  # read available bytes (arrow = 3 bytes)
            except Exception:
                break
            if not data:
                break

            i = 0
            while i < len(data):
                b = data[i]
                if b == 0x1b and i + 2 < len(data) and data[i + 1] == ord("["):
                    # Arrow key escape sequence: ESC [ A/B/C/D
                    arrow = data[i + 2]
                    if arrow == ord("A"):
                        self._handle_arrow_up()
                    elif arrow == ord("B"):
                        self._handle_arrow_down()
                    i += 3
                else:
                    self._handle_char(chr(b))
                    i += 1

    def _handle_char(self, ch: str):
        with self._lock:
            if ch in "123456":
                idx = int(ch) - 1
                if idx < len(self.config.joint_names):
                    self._selected = idx
                    self._print_status()

            elif ch == "7" and self.config.gripper_exist:
                self._selected = len(self.config.joint_names)
                self._print_status()

            elif ch == "r":
                self._positions[:] = self._initial
                self._print_status("RESET")

            elif ch == "0":
                self._positions[:] = 0.0
                self._print_status("HOME")

            elif ch in "+=":
                self._joint_step = min(self._joint_step * 2, 20.0)
                self._gripper_step = min(self._gripper_step * 2, 20.0)
                self._print_status(f"step: j={self._joint_step:.1f} g={self._gripper_step:.1f}")

            elif ch == "-":
                self._joint_step = max(self._joint_step / 2, 0.1)
                self._gripper_step = max(self._gripper_step / 2, 0.5)
                self._print_status(f"step: j={self._joint_step:.1f} g={self._gripper_step:.1f}")

            elif ch == "w":
                self._do_step_up()

            elif ch == "s":
                self._do_step_down()

    def _do_step_up(self):
        step = self._gripper_step if self._selected == len(self.config.joint_names) else self._joint_step
        self._positions[self._selected] += step
        self._print_status()

    def _do_step_down(self):
        step = self._gripper_step if self._selected == len(self.config.joint_names) else self._joint_step
        self._positions[self._selected] -= step
        self._print_status()

    def _handle_arrow_up(self):
        with self._lock:
            self._do_step_up()

    def _handle_arrow_down(self):
        with self._lock:
            self._do_step_down()

    def _print_status(self, msg: str = ""):
        labels = [f"J{i+1}" for i in range(len(self.config.joint_names))]
        if self.config.gripper_exist:
            labels.append("Grip")
        parts = []
        for i, (label, val) in enumerate(zip(labels, self._positions)):
            marker = ">" if i == self._selected else " "
            unit = "mm" if label == "Grip" else "deg"
            parts.append(f"{marker}{label}:{val:+7.1f}{unit}")
        line = " | ".join(parts)
        if msg:
            line += f"  [{msg}]"
        print(f"\r{line}   ", end="", flush=True)
