"""Calibrate a single Piper joint mapping.

Usage:
  python calibrate_single.py <piper_joint>

  piper_joint: 1-6 or 7 (gripper)

Example:
  python calibrate_single.py 1    # calibrate Piper J1 only
"""

import math
import struct
import sys
import selectors

from dynamixel_sdk import PacketHandler, PortHandler

PORT = "/dev/robotis_left"
BAUDRATE = 4_000_000
MOTOR_IDS = [1, 2, 3, 4, 5, 6, 7]
UNITS_PER_REV = 4096
ZERO_OFFSET = 2048

PIPER_JOINTS = {
    1: {"name": "J1 base rotation",  "min_deg": -150.0, "max_deg": 150.0},
    2: {"name": "J2 shoulder",       "min_deg":    0.0, "max_deg": 180.0},
    3: {"name": "J3 elbow",          "min_deg": -170.0, "max_deg":   0.0},
    4: {"name": "J4 wrist roll",     "min_deg": -100.0, "max_deg": 100.0},
    5: {"name": "J5 wrist pitch",    "min_deg":  -70.0, "max_deg":  70.0},
    6: {"name": "J6 wrist rotation", "min_deg": -120.0, "max_deg": 120.0},
    7: {"name": "Gripper",           "min_deg":    0.0, "max_deg":  70.0},
}


def read_all(packet, port):
    rads = []
    for mid in MOTOR_IDS:
        raw, res, err = packet.read4ByteTxRx(port, mid, 132)
        if res != 0 or err != 0:
            rads.append(0.0)
            continue
        signed = struct.unpack("i", struct.pack("I", raw))[0]
        centered = signed - ZERO_OFFSET
        rads.append(centered * 2.0 * math.pi / UNITS_PER_REV)
    return rads


def monitor_until_enter(packet, port, label):
    sel = selectors.DefaultSelector()
    sel.register(sys.stdin, selectors.EVENT_READ)
    print(f"\n  [{label}] Hold position, press Enter.\n")
    last = None
    try:
        while True:
            rads = read_all(packet, port)
            if last is not None:
                print(f"\033[{len(MOTOR_IDS) + 1}A", end="")
            for i, mid in enumerate(MOTOR_IDS):
                deg = rads[i] * 180.0 / math.pi
                delta = ""
                if last is not None:
                    d = abs(rads[i] - last[i])
                    if d > 0.01:
                        delta = f"  ← MOVING"
                print(f"  M{mid}: {rads[i]:+.4f} rad ({deg:>+8.1f}°){delta:20s}")
            print()
            last = rads
            events = sel.select(timeout=0.1)
            if events:
                sys.stdin.readline()
                break
    finally:
        sel.unregister(sys.stdin)
    return rads


def main():
    if len(sys.argv) < 2:
        print("Usage: python calibrate_single.py <piper_joint>")
        print("  piper_joint: 1-6 or 7 (gripper)")
        sys.exit(1)

    pj = int(sys.argv[1])
    info = PIPER_JOINTS[pj]
    min_rad = info["min_deg"] * math.pi / 180.0
    max_rad = info["max_deg"] * math.pi / 180.0

    port = PortHandler(PORT)
    packet = PacketHandler(2.0)
    assert port.openPort()
    assert port.setBaudRate(BAUDRATE)
    for mid in MOTOR_IDS:
        packet.write1ByteTxRx(port, mid, 64, 0)

    print(f"\n  Calibrating: Piper {info['name']} ({info['min_deg']:.0f}° ~ {info['max_deg']:.0f}°)")
    print(f"  Move the corresponding leader joint to one end.")
    pos_a = monitor_until_enter(packet, port, "Position A")

    print(f"  Now move ONLY that joint to the other end.")
    pos_b = monitor_until_enter(packet, port, "Position B")

    port.closePort()

    deltas = [abs(pos_b[i] - pos_a[i]) for i in range(7)]
    best_idx = max(range(7), key=lambda i: deltas[i])

    print(f"\n  Motor movement:")
    for i in range(7):
        marker = " ← DETECTED" if i == best_idx else ""
        print(f"    M{MOTOR_IDS[i]}: {deltas[i]:.3f} rad ({deltas[i]*180/math.pi:.1f}°){marker}")

    override = input(f"\n  Use M{MOTOR_IDS[best_idx]}? (Enter=yes, or type motor ID): ").strip()
    if override:
        best_idx = MOTOR_IDS.index(int(override))

    leader_a = pos_a[best_idx]
    leader_b = pos_b[best_idx]

    print(f"\n  A: leader={leader_a:+.4f}, B: leader={leader_b:+.4f}")
    print(f"  [1] A = Piper {info['min_deg']:.0f}°, B = Piper {info['max_deg']:.0f}°")
    print(f"  [2] A = Piper {info['max_deg']:.0f}°, B = Piper {info['min_deg']:.0f}°")
    choice = input(f"  Direction [1]: ").strip()

    if choice == "2":
        scale = (min_rad - max_rad) / (leader_b - leader_a)
        offset = max_rad - scale * leader_a
    else:
        scale = (max_rad - min_rad) / (leader_b - leader_a)
        offset = min_rad - scale * leader_a

    check_a = (scale * leader_a + offset) * 180 / math.pi
    check_b = (scale * leader_b + offset) * 180 / math.pi

    print(f"\n  Result:")
    print(f"    ({best_idx}, {scale:+.4f}, {offset:+.6f}, {info['min_deg']}, {info['max_deg']}),  # Piper J{pj} ← M{MOTOR_IDS[best_idx]}")
    print(f"\n  Verify: A → {check_a:+.1f}°, B → {check_b:+.1f}°")


if __name__ == "__main__":
    main()
