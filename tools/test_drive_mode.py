"""Check Drive Mode and Homing Offset for all OMY-L100 motors."""
import struct
from dynamixel_sdk import PacketHandler, PortHandler

PORT = "/dev/robotis_left"
BAUDRATE = 4_000_000
PROTOCOL = 2.0
MOTOR_IDS = [1, 2, 3, 4, 5, 6, 7]

# X-series register addresses
ADDR_DRIVE_MODE = 10       # 1 byte
ADDR_HOMING_OFFSET = 20   # 4 bytes
ADDR_PRESENT_POSITION = 132  # 4 bytes

port = PortHandler(PORT)
packet = PacketHandler(PROTOCOL)
assert port.openPort(), f"Failed to open {PORT}"
assert port.setBaudRate(BAUDRATE), f"Failed to set baud rate {BAUDRATE}"

print(f"{'Motor':>6} {'DriveMode':>10} {'Bit0(dir)':>10} {'HomingOffset':>14} {'PresentPos':>12}")
print("-" * 65)

for mid in MOTOR_IDS:
    # Drive Mode
    dm, res, err = packet.read1ByteTxRx(port, mid, ADDR_DRIVE_MODE)
    dm_str = f"{dm} (0b{dm:08b})" if res == 0 and err == 0 else "ERROR"
    dir_bit = "REVERSE" if (dm & 0x01) else "NORMAL" if res == 0 else "?"

    # Homing Offset
    ho_raw, res2, err2 = packet.read4ByteTxRx(port, mid, ADDR_HOMING_OFFSET)
    if res2 == 0 and err2 == 0:
        ho_signed = struct.unpack("i", struct.pack("I", ho_raw))[0]
        ho_str = f"{ho_signed}"
    else:
        ho_str = "ERROR"

    # Present Position
    pp_raw, res3, err3 = packet.read4ByteTxRx(port, mid, ADDR_PRESENT_POSITION)
    if res3 == 0 and err3 == 0:
        pp_signed = struct.unpack("i", struct.pack("I", pp_raw))[0]
        pp_str = f"{pp_signed}"
    else:
        pp_str = "ERROR"

    print(f"  M{mid:>2d}  {dm_str:>18s}  {dir_bit:>8s}  {ho_str:>12s}  {pp_str:>10s}")

port.closePort()
