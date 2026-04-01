"""Send a fake control telemetry packet to localhost:5005 to verify the receiver works."""

import socket
import struct
import binascii

AXES = ["surge", "sway", "heave", "roll", "pitch", "yaw"]
PORT = 5005

# Build a packet matching the firmware format:
# sequence (u32 BE) | setpoint[6] (f32 LE) | output[6] (f32 LE) | error[6] (f32 LE) | crc32 (u32 BE)

sequence = 1
setpoints = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
outputs   = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
errors    = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]

body  = struct.pack(">I", sequence)
body += struct.pack("<6f", *setpoints)
body += struct.pack("<6f", *outputs)
body += struct.pack("<6f", *errors)

crc = binascii.crc32(body) & 0xFFFFFFFF
packet = body + struct.pack(">I", crc)

print(f"Packet size: {len(packet)} bytes (expected 80)")
print(f"CRC: 0x{crc:08X}")

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.sendto(packet, ("127.0.0.1", PORT))
print(f"Sent to 127.0.0.1:{PORT}")
sock.close()
