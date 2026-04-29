"""Send IMU axis configuration to the microcontroller over UDP.

Packet layout (30 bytes, matching axis_config.c on MCU):
  | type (1B)
  | yaw_src (1B) | yaw_sign (1B) | pitch_src (1B) | pitch_sign (1B)
  | roll_src (1B) | roll_sign (1B)
  | ax_src (1B) | ax_sign (1B) | ay_src (1B) | ay_sign (1B)
  | az_src (1B) | az_sign (1B)
  | pad (1B)
  | offset_x (4B float) | offset_y (4B float) | offset_z (4B float)
  | crc32 (4B)

YPR src values: 0=yaw, 1=pitch, 2=roll
Accel src values: 0=x, 1=y, 2=z
sign values: 0=positive, 1=negative
offset: millimeters from IMU to center of mass
"""

import socket
import struct
import zlib

NUCLEO_HOST = "192.168.1.100"
AXIS_CONFIG_PORT = 5004

AXIS_PKT_SET = 0x01

YPR_SRC_MAP = {"yaw": 0, "pitch": 1, "roll": 2}
ACCEL_SRC_MAP = {"x": 0, "y": 1, "z": 2}


def _parse_axis_value(val: str, src_map: dict):
    """Parse '+yaw', '-pitch', '+x', '-z', etc. into (src_index, sign_byte)."""
    sign = 1 if val.startswith("-") else 0
    name = val.lstrip("+-")
    src = src_map.get(name, 0)
    return src, sign


def build_axis_packet(imu_axes: dict, accel_axes: dict, offset: dict) -> bytes:
    """Build a 30-byte axis config SET packet.

    imu_axes:    {"yaw": "+yaw", "pitch": "+pitch", "roll": "+roll"}
    accel_axes:  {"x": "+x", "y": "+y", "z": "+z"}
    offset:      {"x": 0.0, "y": 0.0, "z": 0.0}  (mm)
    """
    yaw_src, yaw_sign = _parse_axis_value(imu_axes.get("yaw", "+yaw"), YPR_SRC_MAP)
    pitch_src, pitch_sign = _parse_axis_value(imu_axes.get("pitch", "+pitch"), YPR_SRC_MAP)
    roll_src, roll_sign = _parse_axis_value(imu_axes.get("roll", "+roll"), YPR_SRC_MAP)

    ax_src, ax_sign = _parse_axis_value(accel_axes.get("x", "+x"), ACCEL_SRC_MAP)
    ay_src, ay_sign = _parse_axis_value(accel_axes.get("y", "+y"), ACCEL_SRC_MAP)
    az_src, az_sign = _parse_axis_value(accel_axes.get("z", "+z"), ACCEL_SRC_MAP)

    off_x = float(offset.get("x", 0.0))
    off_y = float(offset.get("y", 0.0))
    off_z = float(offset.get("z", 0.0))

    # Pack body (everything except CRC)
    body = struct.pack(
        "<BBBBBBB BBBBBB x fff",
        AXIS_PKT_SET,
        yaw_src,
        yaw_sign,
        pitch_src,
        pitch_sign,
        roll_src,
        roll_sign,
        ax_src,
        ax_sign,
        ay_src,
        ay_sign,
        az_src,
        az_sign,
        off_x,
        off_y,
        off_z,
    )
    crc = zlib.crc32(body) & 0xFFFFFFFF
    return body + struct.pack("<I", crc)


def send_axis_config(
    imu_axes: dict = None, accel_axes: dict = None, offset: dict = None, host=NUCLEO_HOST, port=AXIS_CONFIG_PORT
):
    """Send full axis configuration to the microcontroller.

    All three dicts are optional; defaults are identity mapping / zero offset.
    """
    if imu_axes is None:
        imu_axes = {"yaw": "+yaw", "pitch": "+pitch", "roll": "+roll"}
    if accel_axes is None:
        accel_axes = {"x": "+x", "y": "+y", "z": "+z"}
    if offset is None:
        offset = {"x": 0.0, "y": 0.0, "z": 0.0}

    try:
        pkt = build_axis_packet(imu_axes, accel_axes, offset)
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(1.0)
        sock.sendto(pkt, (host, port))
        sock.close()
        print(f"Axis config sent to {host}:{port}: ypr={imu_axes} accel={accel_axes} offset={offset}")
        return True
    except Exception as e:
        print(f"Failed to send axis config: {e}")
        return False
