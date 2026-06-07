"""Control loop telemetry receiver.

Consumes the packed struct emitted by ``control_telemetry.c`` and exposes the
latest setpoint/output/error triplets for each axis so the debug UI can render
10 Hz charts. Packets are structured as::

    sequence (u32 big-endian)
    setpoint[6] (float32 little-endian, surge..yaw)
    output[6]   (float32 little-endian)
    error[6]    (float32 little-endian)
    manipulator_deg (float32 little-endian, optional on newer firmware)
    manipulator_pulse_us (uint16 little-endian, optional on newer firmware)
    crc32 (u32 big-endian)

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
FLOAT_COUNT = len(AXES) * 3
OLD_PACKET_SIZE = 4 + FLOAT_COUNT * 4 + 4
MANIPULATOR_SIZE = struct.calcsize("<fH")
PACKET_SIZE = OLD_PACKET_SIZE + MANIPULATOR_SIZE
HISTORY_CAPACITY = 3000  # 5 minutes @ 10 Hz
LOG_DIR = logs_dir()
CONTROL_LOG = log_path("control_telemetry.ndjson")


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

    # Internal helpers -------------------------------------------------
    def _handle_packet(self, data: bytes, addr: tuple[str, int]):
        if len(data) not in (OLD_PACKET_SIZE, PACKET_SIZE):
            print(
                f"Control telemetry: invalid packet size from {addr}: "
                f"{len(data)} bytes (expected {OLD_PACKET_SIZE} or {PACKET_SIZE})"
            )
            return
        body = data[:-4]
        crc = struct.unpack("!I", data[-4:])[0]
        calc = crc32_ieee(body)
        if calc != crc:
            print(f"Control telemetry: CRC mismatch (calc=0x{calc:08X}, recv=0x{crc:08X})")
            return
        sequence = struct.unpack("!I", body[:4])[0]
        float_end = 4 + FLOAT_COUNT * 4
        floats = struct.unpack("<" + "f" * FLOAT_COUNT, body[4:float_end])
        setpoints = dict(zip(AXES, floats[0:6]))
        outputs = dict(zip(AXES, floats[6:12]))
        errors = dict(zip(AXES, floats[12:18]))
        manipulator = {}
        if len(data) == PACKET_SIZE:
            manip_offset = float_end
            manip_deg, manip_pulse_us = struct.unpack("<fH", body[manip_offset : manip_offset + MANIPULATOR_SIZE])
            manipulator = {"deg": round(manip_deg, 2), "pulse_us": int(manip_pulse_us)}
        snapshot = {
            "sequence": sequence,
            "timestamp": time.time(),
            "setpoint": {k: round(v, 4) for k, v in setpoints.items()},
            "output": {k: round(v, 4) for k, v in outputs.items()},
            "error": {k: round(v, 4) for k, v in errors.items()},
            "manipulator": manipulator,
        }
        with self._lock:
            self._latest = snapshot
            self._history.append(snapshot)
        try:
            self.data_handler.update_data({"control_telemetry": snapshot})
        except Exception as exc:
            print(f"Control telemetry: failed to persist snapshot: {exc}")
        if self._capture_enabled:
            self._append_log(snapshot)

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
