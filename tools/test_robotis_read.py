"""Debug script: read OMY-L100 motor positions (X-series motors!)."""
import math
import struct
import time

from dynamixel_sdk import PacketHandler, PortHandler

PORT = "/dev/robotis_left"
BAUDRATE = 4_000_000
PROTOCOL = 2.0
MOTOR_IDS = [1, 2, 3, 4, 5, 6, 7]

# X-series register addresses (XH540, XC330)
ADDR_TORQUE_ENABLE = 64
ADDR_PRESENT_POSITION = 132
LEN_PRESENT_POSITION = 4

# X-series: 4096 units = 1 revolution = 2π rad, center at 2048
UNITS_PER_REV = 4096
ZERO_OFFSET = 2048

port = PortHandler(PORT)
packet = PacketHandler(PROTOCOL)
assert port.openPort(), f"Failed to open {PORT}"
assert port.setBaudRate(BAUDRATE), f"Failed to set baud rate {BAUDRATE}"

print(f"Port: {PORT}, Baudrate: {BAUDRATE}\n")

# Step 1: Ping and show model numbers
print("=== Motor scan ===")
for mid in MOTOR_IDS:
    model, result, error = packet.ping(port, mid)
    if result != 0:
        print(f"  Motor {mid}: COMM ERROR")
    else:
        print(f"  Motor {mid}: model={model}, error={error}")

# Step 2: Disable torque
print("\n=== Disable torque (addr 64) ===")
for mid in MOTOR_IDS:
    result, error = packet.write1ByteTxRx(port, mid, ADDR_TORQUE_ENABLE, 0)
    status = "OK" if result == 0 and error == 0 else f"result={result} error={error}"
    print(f"  Motor {mid}: {status}")

# Step 3: Read positions
print("\n=== Read positions (Ctrl+C to stop) ===")
print("Move the leader arm to see values change.\n")

try:
    while True:
        print(f"{'Motor':>6} {'Raw':>10} {'Ctr':>6} {'rad':>8} {'deg':>8}")
        print("-" * 45)
        for mid in MOTOR_IDS:
            raw, result, error = packet.read4ByteTxRx(port, mid, ADDR_PRESENT_POSITION)
            if result != 0 or error != 0:
                print(f"  M{mid:>2d}  READ FAIL (result={result}, error={error})")
                continue
            signed = struct.unpack("i", struct.pack("I", raw))[0]
            centered = signed - ZERO_OFFSET
            rad = centered * 2.0 * math.pi / UNITS_PER_REV
            deg = rad * 180.0 / math.pi
            print(f"  M{mid:>2d}  {signed:>10d}  {centered:>+6d}  {rad:>+8.4f}  {deg:>+8.2f}°")
        print()
        time.sleep(0.5)
except KeyboardInterrupt:
    print("\nDone.")
finally:
    port.closePort()
