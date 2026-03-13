"""Calibration wizard: map OMY-L100 leader joints → Piper follower joints.

For each Piper joint:
  1. Move the leader joint to one end → press Enter (live display shows all motors)
  2. Move to the other end → press Enter
  3. Tool auto-detects which motor moved most
  4. You pick which Piper joint and direction

No need to know any angle values.
"""

import math
import struct
import sys
import time
import selectors

from dynamixel_sdk import PacketHandler, PortHandler

PORT = "/dev/robotis_left"
BAUDRATE = 4_000_000
PROTOCOL = 2.0
MOTOR_IDS = [1, 2, 3, 4, 5, 6, 7]
UNITS_PER_REV = 4096
ZERO_OFFSET = 2048

# Piper joint limits (from URDF, in radians)
PIPER_JOINTS = {
    1: {"name": "J1 base rotation",  "min_rad": -2.618,  "max_rad": 2.618,  "min_deg": -150.0, "max_deg": 150.0},
    2: {"name": "J2 shoulder",       "min_rad":  0.0,    "max_rad": 3.14,   "min_deg":    0.0, "max_deg": 180.0},
    3: {"name": "J3 elbow",          "min_rad": -2.967,  "max_rad": 0.0,    "min_deg": -170.0, "max_deg":   0.0},
    4: {"name": "J4 wrist roll",     "min_rad": -1.745,  "max_rad": 1.745,  "min_deg": -100.0, "max_deg": 100.0},
    5: {"name": "J5 wrist pitch",    "min_rad": -1.22,   "max_rad": 1.22,   "min_deg":  -70.0, "max_deg":  70.0},
    6: {"name": "J6 wrist rotation", "min_rad": -2.0944, "max_rad": 2.0944, "min_deg": -120.0, "max_deg": 120.0},
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
        rad = centered * 2.0 * math.pi / UNITS_PER_REV
        rads.append(rad)
    return rads


def monitor_until_enter(packet, port, label):
    """Show live motor positions. Return snapshot when Enter is pressed."""
    sel = selectors.DefaultSelector()
    sel.register(sys.stdin, selectors.EVENT_READ)

    print(f"\n  [{label}] Hold position and press Enter to record.\n")

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
                        delta = f"  ← MOVING ({d:.3f})"
                print(f"  M{mid}: {rads[i]:+.4f} rad  ({deg:>+8.1f}°){delta:30s}")
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
    port = PortHandler(PORT)
    packet = PacketHandler(PROTOCOL)
    assert port.openPort(), f"Failed to open {PORT}"
    assert port.setBaudRate(BAUDRATE), f"Failed to set baud rate {BAUDRATE}"

    for mid in MOTOR_IDS:
        packet.write1ByteTxRx(port, mid, 64, 0)

    print("=" * 60)
    print("  OMY-L100 → Piper Joint Mapping Calibration")
    print("=" * 60)
    print()
    print("  You will map 6 joints + gripper (7 rounds).")
    print("  Each round: move ONE leader joint to two positions.")
    print("  Only move the LEADER arm, not the Piper.")
    print()

    results = []
    mapped_piper = set()

    for round_num in range(7):
        is_gripper = (round_num == 6)

        print(f"\n{'─' * 60}")
        if is_gripper:
            print(f"  Round 7/7: GRIPPER")
        else:
            remaining = [j for j in range(1, 7) if j not in mapped_piper]
            print(f"  Round {round_num + 1}/7")
            print(f"  Remaining Piper joints: {remaining}")
        print(f"{'─' * 60}")

        print(f"\n  Move ONE leader joint to one end of its range.")
        pos_a = monitor_until_enter(packet, port, "Position A")

        print(f"  Now move ONLY that same joint to the OTHER end.")
        pos_b = monitor_until_enter(packet, port, "Position B")

        # Find which motor moved the most
        deltas = [abs(pos_b[i] - pos_a[i]) for i in range(7)]
        best_idx = max(range(7), key=lambda i: deltas[i])
        best_mid = MOTOR_IDS[best_idx]

        print(f"  Motor movement:")
        for i in range(7):
            marker = " ← DETECTED" if i == best_idx else ""
            print(f"    M{MOTOR_IDS[i]}: {deltas[i]:.3f} rad ({deltas[i]*180/math.pi:.1f}°){marker}")

        # Override motor if needed
        override = input(f"\n  Use M{best_mid}? (Enter=yes, or type motor ID): ").strip()
        if override:
            best_mid = int(override)
            best_idx = MOTOR_IDS.index(best_mid)

        leader_a = pos_a[best_idx]
        leader_b = pos_b[best_idx]

        if is_gripper:
            piper_joint = 7
            piper_min_rad = 0.0
            piper_max_rad = 0.070  # 70mm
        else:
            remaining = [j for j in range(1, 7) if j not in mapped_piper]
            pj = input(f"  Which Piper joint? {remaining}: ").strip()
            piper_joint = int(pj)
            info = PIPER_JOINTS[piper_joint]
            piper_min_rad = info["min_rad"]
            piper_max_rad = info["max_rad"]
            print(f"  → Piper {info['name']} ({info['min_deg']:.0f}° ~ {info['max_deg']:.0f}°)")

        # Direction
        print(f"\n  Position A: leader = {leader_a:+.3f} rad")
        print(f"  Position B: leader = {leader_b:+.3f} rad")
        if is_gripper:
            print(f"  [1] A = gripper closed, B = gripper open")
            print(f"  [2] A = gripper open,   B = gripper closed")
        else:
            print(f"  [1] A = Piper min ({PIPER_JOINTS[piper_joint]['min_deg']:.0f}°),  B = Piper max ({PIPER_JOINTS[piper_joint]['max_deg']:.0f}°)")
            print(f"  [2] A = Piper max ({PIPER_JOINTS[piper_joint]['max_deg']:.0f}°),  B = Piper min ({PIPER_JOINTS[piper_joint]['min_deg']:.0f}°)")

        choice = input(f"  Direction [1]: ").strip()
        reverse = (choice == "2")

        # Compute: piper_rad = scale * leader_rad + offset
        if reverse:
            scale = (piper_min_rad - piper_max_rad) / (leader_b - leader_a)
            offset = piper_max_rad - scale * leader_a
        else:
            scale = (piper_max_rad - piper_min_rad) / (leader_b - leader_a)
            offset = piper_min_rad - scale * leader_a

        check_a = scale * leader_a + offset
        check_b = scale * leader_b + offset
        R2D = 180.0 / math.pi

        if is_gripper:
            print(f"\n  Result: scale={scale:+.4f}, offset={offset:+.6f}")
            print(f"  Verify: A → {check_a*1000:.1f}mm, B → {check_b*1000:.1f}mm")
        else:
            print(f"\n  Result: scale={scale:+.4f}, offset={offset:+.6f} rad")
            print(f"  Verify: A → {check_a*R2D:+.1f}°, B → {check_b*R2D:+.1f}°")

        if not is_gripper:
            mapped_piper.add(piper_joint)

        results.append({
            "piper_joint": piper_joint,
            "leader_index": best_idx,
            "motor_id": best_mid,
            "scale": scale,
            "offset_rad": offset,
        })

        print(f"  ✓ Saved!")

    port.closePort()

    # Output
    joints = sorted([r for r in results if r["piper_joint"] <= 6], key=lambda r: r["piper_joint"])
    grip = [r for r in results if r["piper_joint"] == 7]

    print(f"\n\n{'=' * 60}")
    print("  CALIBRATION COMPLETE")
    print(f"{'=' * 60}\n")

    print("    joint_mapping: list[tuple] = field(default_factory=lambda: [")
    for r in joints:
        info = PIPER_JOINTS[r["piper_joint"]]
        print(f"        ({r['leader_index']}, {r['scale']:+.4f}, {r['offset_rad']:+.6f}, "
              f"{info['min_deg']:.1f}, {info['max_deg']:.1f}),  "
              f"# Piper J{r['piper_joint']} ← M{r['motor_id']}")
    print("    ])")

    if grip:
        g = grip[0]
        if g["scale"] > 0:
            closed_rad, open_rad = g["offset_rad"] / -g["scale"], (0.070 - g["offset_rad"]) / g["scale"]
        else:
            closed_rad, open_rad = (0.070 - g["offset_rad"]) / g["scale"], g["offset_rad"] / -g["scale"]
        # Simpler: use recorded positions
        print(f"\n    gripper_leader_index: int = {g['leader_index']}")
        print(f"    # Gripper scale={g['scale']:+.4f}, offset={g['offset_rad']:+.6f}")

    print(f"\n{'=' * 60}")


if __name__ == "__main__":
    main()
