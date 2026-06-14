"""Control loop telemetry receiver.

Consumes the packed struct emitted by ``control_telemetry.c`` and exposes the
latest setpoint, measurement, output, error, gain, and input values for each
axis. The decoder accepts the older compact packet too, so Topside can still
show partial telemetry if the MCU has not been flashed yet.

The CRC covers the bytes up to but excluding the CRC field.
"""

from __future__ import annotations

import json
import struct
import threading
import time
from collections import deque
from typing import Deque, Dict, List

from lib.crc import crc32_ieee
from lib.json_data_handler import JSONDataHandler
from lib.net_transport import UdpConfig, UdpListener
from lib.runtime_paths import log_path, logs_dir

CONTROL_TELEM_PORT = 5005
AXES = ["surge", "sway", "heave", "roll", "pitch", "yaw"]
PID_GAINS = ["kp", "ki", "kd"]
OLD_FLOAT_COUNT = len(AXES) * 3
OLD_PACKET_SIZE = 4 + OLD_FLOAT_COUNT * 4 + struct.calcsize("<fH") + 4
NEW_META_FORMAT = "<BBB6bBb"
NEW_META_SIZE = struct.calcsize(NEW_META_FORMAT)
NEW_FLOAT_COUNT = len(AXES) * 7
NEW_PACKET_SIZE = 12 + NEW_META_SIZE + NEW_FLOAT_COUNT * 4 + struct.calcsize("<fH") + 4
PACKET_SIZE = NEW_PACKET_SIZE
HISTORY_CAPACITY = 3000  # 5 minutes @ 10 Hz
LOG_DIR = logs_dir()
CONTROL_LOG = log_path("control_telemetry.ndjson")
FLAG_TIMEOUT = 0x01
FLAG_OVERRIDE = 0x02
FLAG_PID = 0x04


class ControlTelemetryReceiver:
    def __init__(
        self, host: str = "0.0.0.0", port: int = CONTROL_TELEM_PORT, data_handler: JSONDataHandler | None = None
    ):
        self.host = host
        self.port = port
        self.data_handler = data_handler or JSONDataHandler()
        self._listener: UdpListener | None = None
        self._lock = threading.Lock()
        self._latest: Dict[str, dict] = {}
        self._history: Deque[dict] = deque(maxlen=HISTORY_CAPACITY)
        self._capture_enabled = True
        self._packet_count = 0
        self._crc_errors = 0
        self._invalid_packets = 0
        self._last_addr: tuple[str, int] | None = None
        LOG_DIR.mkdir(parents=True, exist_ok=True)

    def start(self) -> None:
        if self._listener is not None:
            return
        cfg = UdpConfig(host=self.host, port=self.port, broadcast=True, timeout=1.0, recv_buffer=2048)
        self._listener = UdpListener("ControlTelemetry", cfg, self._handle_packet)
        self._listener.start()
        print(f"Control telemetry receiver started on {self.host}:{self.port}")

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()
            self._listener = None
        print("Control telemetry receiver stopped")

    def enable_capture(self) -> None:
        self._capture_enabled = True

    def disable_capture(self) -> None:
        self._capture_enabled = False

    def get_latest(self) -> dict:
        with self._lock:
            return self._latest.copy()

    def get_history(self, limit: int = 120) -> List[dict]:
        """Return up to *limit* most recent telemetry samples."""

        limit = max(1, min(limit, HISTORY_CAPACITY))
        with self._lock:
            if not self._history:
                return []
            hist_list = list(self._history)
        return hist_list[-limit:]

    def get_stats(self) -> dict:
        with self._lock:
            latest = self._latest.copy()
            last_ts = latest.get("timestamp")
            age_ms = None if last_ts is None else max(0.0, (time.time() - last_ts) * 1000.0)
            return {
                "packet_count": self._packet_count,
                "crc_errors": self._crc_errors,
                "invalid_packets": self._invalid_packets,
                "last_sequence": latest.get("sequence"),
                "last_age_ms": age_ms,
                "last_addr": list(self._last_addr) if self._last_addr else None,
                "protocol_version": latest.get("protocol_version"),
            }

    # Internal helpers -------------------------------------------------
    def _handle_packet(self, data: bytes, addr: tuple[str, int]):
        if len(data) not in (OLD_PACKET_SIZE, NEW_PACKET_SIZE):
            with self._lock:
                self._invalid_packets += 1
            print(
                "Control telemetry: invalid packet size from "
                f"{addr}: {len(data)} bytes (expected {OLD_PACKET_SIZE} or {NEW_PACKET_SIZE})"
            )
            return
        body = data[:-4]
        crc = struct.unpack("!I", data[-4:])[0]
        calc = crc32_ieee(body)
        if calc != crc:
            with self._lock:
                self._crc_errors += 1
            print(f"Control telemetry: CRC mismatch (calc=0x{calc:08X}, recv=0x{crc:08X})")
            return
        if len(data) == NEW_PACKET_SIZE:
            snapshot = self._decode_v2(body)
        else:
            snapshot = self._decode_v1(body)
        snapshot["timestamp"] = time.time()
        snapshot["source"] = {"host": addr[0], "port": addr[1]}
        with self._lock:
            self._packet_count += 1
            self._last_addr = addr
            self._latest = snapshot
            self._history.append(snapshot)
        try:
            self.data_handler.update_data({"control_telemetry": snapshot})
        except Exception as exc:
            print(f"Control telemetry: failed to persist snapshot: {exc}")
        if self._capture_enabled:
            self._append_log(snapshot)

    def _decode_v1(self, body: bytes) -> dict:
        sequence = struct.unpack("!I", body[:4])[0]
        float_end = 4 + OLD_FLOAT_COUNT * 4
        floats = struct.unpack("<" + "f" * OLD_FLOAT_COUNT, body[4:float_end])
        setpoints = dict(zip(AXES, floats[0:6]))
        outputs = dict(zip(AXES, floats[6:12]))
        errors = dict(zip(AXES, floats[12:18]))
        manip_deg, manip_pulse_us = struct.unpack("<fH", body[float_end:])
        snapshot = {
            "protocol_version": 1,
            "sequence": sequence,
            "setpoint": {k: round(v, 4) for k, v in setpoints.items()},
            "measurement": {},
            "output": {k: round(v, 4) for k, v in outputs.items()},
            "error": {k: round(v, 4) for k, v in errors.items()},
            "gains": {},
            "pilot_raw": {},
            "pilot_norm": {},
            "light": None,
            "manipulator_command": None,
            "flags_raw": 0,
            "flags": {"timeout": False, "override": False, "pid": False},
            "override_mask": 0,
            "pid_active_mask": 0,
            "mcu_uptime_ms": None,
            "last_command_age_ms": None,
            "manipulator": {"deg": round(manip_deg, 2), "pulse_us": int(manip_pulse_us)},
        }
        return snapshot

    def _decode_v2(self, body: bytes) -> dict:
        sequence, mcu_uptime_ms, last_command_age_ms = struct.unpack("!III", body[:12])
        meta_start = 12
        meta_end = meta_start + NEW_META_SIZE
        flags, override_mask, pid_active_mask, *rest = struct.unpack(NEW_META_FORMAT, body[meta_start:meta_end])
        pilot_values = rest[:6]
        light = rest[6]
        manipulator_command = rest[7]
        float_start = meta_end
        float_end = float_start + NEW_FLOAT_COUNT * 4
        floats = struct.unpack("<" + "f" * NEW_FLOAT_COUNT, body[float_start:float_end])

        idx = 0
        setpoints = dict(zip(AXES, floats[idx : idx + 6]))
        idx += 6
        measurements = dict(zip(AXES, floats[idx : idx + 6]))
        idx += 6
        outputs = dict(zip(AXES, floats[idx : idx + 6]))
        idx += 6
        errors = dict(zip(AXES, floats[idx : idx + 6]))
        idx += 6
        gain_values = floats[idx : idx + 18]
        gains = {}
        for axis_index, axis in enumerate(AXES):
            base = axis_index * 3
            gains[axis] = {
                "kp": round(gain_values[base], 6),
                "ki": round(gain_values[base + 1], 6),
                "kd": round(gain_values[base + 2], 6),
            }

        manip_deg, manip_pulse_us = struct.unpack("<fH", body[float_end:])
        pilot_raw = dict(zip(AXES, pilot_values))
        pilot_norm = {axis: round(value / 127.0, 4) for axis, value in pilot_raw.items()}
        return {
            "protocol_version": 2,
            "sequence": sequence,
            "mcu_uptime_ms": mcu_uptime_ms,
            "last_command_age_ms": last_command_age_ms,
            "flags_raw": flags,
            "flags": {
                "timeout": bool(flags & FLAG_TIMEOUT),
                "override": bool(flags & FLAG_OVERRIDE),
                "pid": bool(flags & FLAG_PID),
            },
            "override_mask": override_mask,
            "pid_active_mask": pid_active_mask,
            "pilot_raw": pilot_raw,
            "pilot_norm": pilot_norm,
            "light": int(light),
            "manipulator_command": int(manipulator_command),
            "setpoint": {k: round(v, 4) for k, v in setpoints.items()},
            "measurement": {k: round(v, 4) for k, v in measurements.items()},
            "output": {k: round(v, 4) for k, v in outputs.items()},
            "error": {k: round(v, 4) for k, v in errors.items()},
            "gains": gains,
            "manipulator": {"deg": round(manip_deg, 2), "pulse_us": int(manip_pulse_us)},
        }

    def _append_log(self, snapshot: dict) -> None:
        try:
            with CONTROL_LOG.open("a", encoding="utf-8") as fp:
                fp.write(json.dumps(snapshot) + "\n")
        except OSError as exc:
            print(f"Control telemetry: failed to log snapshot: {exc}")


def init_control_telemetry(
    host: str = "0.0.0.0", port: int = CONTROL_TELEM_PORT, data_handler: JSONDataHandler | None = None
) -> ControlTelemetryReceiver:
    receiver = ControlTelemetryReceiver(host=host, port=port, data_handler=data_handler)
    receiver.start()
    return receiver
