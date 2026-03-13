"""Compare our direct motor reads with the robotis2piper.py mapping.

Run with the leader arm in any pose. Shows:
1. Our raw reads (with center offset)
2. What the robotis2piper.py mapping would produce from these values
   (both with and without Drive Mode negation)

This helps verify if our reads match the ROS2 system.
"""

import math
import struct
from dynamixel_sdk import PacketHandler, PortHandler

PORT = "/dev/robotis_left"
BAUDRATE = 4_000_000
PROTOCOL = 2.0
MOTOR_IDS = [1, 2, 3, 4, 5, 6, 7]
UNITS_PER_REV = 4096
ZERO_OFFSET = 2048

port = PortHandler(PORT)
packet = PacketHandler(PROTOCOL)
assert port.openPort(), f"Failed to open {PORT}"
assert port.setBaudRate(BAUDRATE), f"Failed to set baud rate {BAUDRATE}"

# Read Drive Modes
drive_modes = {}
for mid in MOTOR_IDS:
    dm, res, err = packet.read1ByteTxRx(port, mid, 10)
    drive_modes[mid] = dm if res == 0 else 0

# Disable torque
for mid in MOTOR_IDS:
    packet.write1ByteTxRx(port, mid, 64, 0)

# Read positions
rads_raw = []
for mid in MOTOR_IDS:
    raw, res, err = packet.read4ByteTxRx(port, mid, 132)
    signed = struct.unpack("i", struct.pack("I", raw))[0]
    centered = signed - ZERO_OFFSET
    rad = centered * 2.0 * math.pi / UNITS_PER_REV
    rads_raw.append(rad)

port.closePort()

print("=" * 70)
print("  Motor Readings")
print("=" * 70)
print(f"{'Motor':>6} {'DriveMode':>10} {'Raw rad':>10} {'Negated rad':>12}")
print("-" * 45)
for i, mid in enumerate(MOTOR_IDS):
    dm = drive_modes[mid]
    is_rev = bool(dm & 0x01)
    neg = -rads_raw[i] if is_rev else rads_raw[i]
    flag = " (REV)" if is_rev else ""
    print(f"  M{mid}  DM={dm}{flag:>6s}  {rads_raw[i]:>+8.4f}  {neg:>+8.4f}")

R2D = 180.0 / math.pi

def apply_mapping(leader, label):
    """Apply robotis2piper.py mapping and show results."""
    j1 = max(-1.7453, min(leader[3], 1.7453))
    j2 = max(0.0, min(leader[5] + 1.57, 2.618))
    j3 = max(-2.618, min(leader[4] - 2.66, 0.0))
    j4 = max(-1.7453, min(leader[1] - 1.57, 1.7453))
    j5 = max(-1.2217, min(leader[2] + 1.57, 1.2217))
    j6 = max(-1.7453, min(leader[0] * -1.0 + 0.33, 1.7453))
    grip = max(0.0, min((leader[6] + 0.8) * 0.04375, 0.035))

    print(f"\n{'=' * 70}")
    print(f"  Piper Targets — {label}")
    print(f"{'=' * 70}")
    print(f"  J1 (base):    {j1:>+8.4f} rad = {j1*R2D:>+8.1f}°  ← leader[3]={leader[3]:+.4f}")
    print(f"  J2 (shoulder):{j2:>+8.4f} rad = {j2*R2D:>+8.1f}°  ← leader[5]={leader[5]:+.4f} + 1.57")
    print(f"  J3 (elbow):   {j3:>+8.4f} rad = {j3*R2D:>+8.1f}°  ← leader[4]={leader[4]:+.4f} - 2.66")
    print(f"  J4 (wrist R): {j4:>+8.4f} rad = {j4*R2D:>+8.1f}°  ← leader[1]={leader[1]:+.4f} - 1.57")
    print(f"  J5 (wrist P): {j5:>+8.4f} rad = {j5*R2D:>+8.1f}°  ← leader[2]={leader[2]:+.4f} + 1.57")
    print(f"  J6 (wrist Y): {j6:>+8.4f} rad = {j6*R2D:>+8.1f}°  ← leader[0]={leader[0]:+.4f} * -1 + 0.33")
    print(f"  Gripper:      {grip:.4f} m                 ← leader[6]={leader[6]:+.4f}")

    # Flag clamped joints
    clamped = []
    checks = [
        ("J1", leader[3], -1.7453, 1.7453),
        ("J2", leader[5]+1.57, 0.0, 2.618),
        ("J3", leader[4]-2.66, -2.618, 0.0),
        ("J4", leader[1]-1.57, -1.7453, 1.7453),
        ("J5", leader[2]+1.57, -1.2217, 1.2217),
        ("J6", leader[0]*-1+0.33, -1.7453, 1.7453),
    ]
    for name, val, lo, hi in checks:
        if val <= lo or val >= hi:
            print(f"  ⚠ {name} CLAMPED (raw value {val:.4f} outside [{lo:.4f}, {hi:.4f}])")


# Version A: as-is (no Drive Mode correction)
apply_mapping(rads_raw, "WITHOUT Drive Mode negation (as-is)")

# Version B: negate REVERSE motors
rads_corrected = []
for i, mid in enumerate(MOTOR_IDS):
    if drive_modes[mid] & 0x01:
        rads_corrected.append(-rads_raw[i])
    else:
        rads_corrected.append(rads_raw[i])

apply_mapping(rads_corrected, "WITH Drive Mode negation (M2,M4,M6 negated)")

print(f"\n{'=' * 70}")
print("  Compare the two versions above.")
print("  If 'WITH negation' has fewer clamped joints and more")
print("  reasonable values, the Drive Mode fix is correct.")
print(f"{'=' * 70}")
