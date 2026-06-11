import socket
import struct
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from lib.crc import crc32_ieee

AXES = ["surge", "sway", "heave", "roll", "pitch", "yaw"]
PORT = 5005


def build_packet() -> bytes:
    """Build a packet matching the firmware control telemetry format."""
    sequence = 1
    setpoints = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    outputs = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    errors = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]

    body = struct.pack(">I", sequence)
    body += struct.pack("<6f", *setpoints)
    body += struct.pack("<6f", *outputs)
    body += struct.pack("<6f", *errors)
    body += struct.pack("<fH", 0.0, 1500)

    crc = crc32_ieee(body)
    packet = body + struct.pack(">I", crc)

    print(f"Packet size: {len(packet)} bytes (expected 86)")
    print(f"CRC: 0x{crc:08X}")
    return packet


def main() -> None:
    packet = build_packet()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.sendto(packet, ("127.0.0.1", PORT))
        print(f"Sent to 127.0.0.1:{PORT}")
    finally:
        sock.close()


if __name__ == "__main__":
    main()
