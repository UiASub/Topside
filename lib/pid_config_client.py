"""
PID Config Client - sends/receives PID gain packets to/from the MCU over UDP.

Packet layout (77 bytes, little-endian, matches pid_config.c on the MCU):
  | type (1B) | surge P,I,D (12B) | sway P,I,D (12B) | heave P,I,D (12B)
  | roll P,I,D (12B) | pitch P,I,D (12B) | yaw P,I,D (12B) | crc32 (4B) |

type 0x01 = SET (write new gains), type 0x02 = REQUEST (read current gains).
Both operations return a reply with the active gains.
"""

import socket
import struct
import zlib

from lib.net_transport import DEFAULT_ROV_HOST

MCU_IP = DEFAULT_ROV_HOST
PID_CONFIG_PORT = 5003

PID_PKT_SET = 0x01
PID_PKT_REQUEST = 0x02

AXES = ["surge", "sway", "heave", "roll", "pitch", "yaw"]

# type(1B) + 18 floats(72B) + crc32(4B) = 77 bytes, little-endian (ARM native)
PACKET_FORMAT = "<B18fI"
PACKET_SIZE = struct.calcsize(PACKET_FORMAT)  # 77


def _build_packet(pkt_type, gains):
    """Pack a PID packet with CRC.
    gains: dict  axis -> {"kp": float, "ki": float, "kd": float}
    """
    floats = []
    for axis in AXES:
        g = gains.get(axis, {"kp": 0.0, "ki": 0.0, "kd": 0.0})
        floats.extend([float(g["kp"]), float(g["ki"]), float(g["kd"])])

    header = struct.pack("<B18f", pkt_type, *floats)
    crc = zlib.crc32(header) & 0xFFFFFFFF
    return header + struct.pack("<I", crc)


def _parse_packet(data):
    """Unpack a PID reply packet. Returns gains dict or None on CRC error."""
    if len(data) != PACKET_SIZE:
        return None

    values = struct.unpack(PACKET_FORMAT, data)
    recv_crc = values[19]

    calc_crc = zlib.crc32(data[:-4]) & 0xFFFFFFFF
    if calc_crc != recv_crc:
        return None

    floats = values[1:19]
    gains = {}
    for i, axis in enumerate(AXES):
        gains[axis] = {
            "kp": round(floats[i * 3], 6),
            "ki": round(floats[i * 3 + 1], 6),
            "kd": round(floats[i * 3 + 2], 6),
        }
    return gains


def _gains_match(sent, received):
    """Check whether the MCU confirmed the exact gains we sent."""
    for axis in AXES:
        for k in ("kp", "ki", "kd"):
            # Compare as 32-bit floats to avoid precision mismatch
            s = struct.pack("<f", float(sent.get(axis, {}).get(k, 0.0)))
            r = struct.pack("<f", float(received.get(axis, {}).get(k, 0.0)))
            if s != r:
                return False
    return True


def send_pid_gains(gains, timeout=1.0, max_retries=3, host=MCU_IP):
    """Send PID gains to MCU, verify the reply matches, retry if lost.

    Returns (confirmed_gains, attempts) on success, or (None, attempts) if
    all retries failed.
    """
    packet = _build_packet(PID_PKT_SET, gains)

    for attempt in range(1, max_retries + 1):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        try:
            sock.sendto(packet, (host, PID_CONFIG_PORT))
            data, _ = sock.recvfrom(1024)
            confirmed = _parse_packet(data)
            if confirmed is not None and _gains_match(gains, confirmed):
                return confirmed, attempt
            # CRC failed or values didn't match — retry
        except socket.timeout:
            pass  # no reply — retry
        finally:
            sock.close()

    return None, max_retries


def request_pid_gains(timeout=2.0, host=MCU_IP):
    """Request current PID gains from MCU (REQUEST). Returns gains dict or None."""
    empty = {axis: {"kp": 0.0, "ki": 0.0, "kd": 0.0} for axis in AXES}
    packet = _build_packet(PID_PKT_REQUEST, empty)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    try:
        sock.sendto(packet, (host, PID_CONFIG_PORT))
        data, _ = sock.recvfrom(1024)
        return _parse_packet(data)
    except socket.timeout:
        return None
    finally:
        sock.close()
