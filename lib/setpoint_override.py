"""Setpoint override client for the control firmware."""

from __future__ import annotations

import struct
import threading
import time
from dataclasses import dataclass, field
from typing import Dict

from lib.crc import crc32_ieee
from lib.net_transport import DEFAULT_ROV_HOST, UdpSender

AXES = ["surge", "sway", "heave", "roll", "pitch", "yaw"]
AXIS_BITS = {axis: idx for idx, axis in enumerate(AXES)}
SETPOINT_OVERRIDE_PORT = 5007
TYPE_SET = 0x01
TYPE_CLEAR = 0x02


@dataclass
class OverrideState:
    active: bool = False
    axes: Dict[str, float] = field(default_factory=lambda: {axis: 0.0 for axis in AXES})
    last_error: str | None = None
    last_update_ts: float = 0.0


class SetpointOverrideClient:
    def __init__(self, host: str = DEFAULT_ROV_HOST, port: int = SETPOINT_OVERRIDE_PORT, resource_monitor=None):
        self.host = host
        self.port = port
        self.sender = UdpSender(host, port)
        self.resource_monitor = resource_monitor
        self._state = OverrideState()
        self._lock = threading.Lock()
        self._last_resource_errors = 0

    def close(self) -> None:
        self.sender.close()

    def _check_resource_health(self) -> None:
        if not self.resource_monitor:
            return
        counters = getattr(self.resource_monitor, "get_udp_counters", None)
        if not counters:
            return
        _rx, errors = counters()
        if errors > self._last_resource_errors:
            raise RuntimeError("Resource monitor reports increasing UDP RX errors; refusing to send override")
        self._last_resource_errors = errors

    def send_override(self, axes: Dict[str, float], replay_attempts: int = 3, replay_delay: float = 0.05) -> dict:
        self._check_resource_health()
        values = [0.0] * len(AXES)
        axis_mask = 0
        for axis, value in axes.items():
            if axis not in AXIS_BITS:
                continue
            idx = AXIS_BITS[axis]
            axis_mask |= 1 << idx
            values[idx] = float(value)
        if axis_mask == 0:
            raise ValueError("No valid axes provided for override")
        body = struct.pack("BB", TYPE_SET, axis_mask) + struct.pack("<" + "f" * len(values), *values)
        crc = crc32_ieee(body)
        packet = body + struct.pack("<I", crc & 0xFFFFFFFF)
        for attempt in range(max(1, replay_attempts)):
            self.sender.send(packet)
            if attempt + 1 < replay_attempts:
                time.sleep(replay_delay)
        with self._lock:
            self._state.active = True
            for axis, value in axes.items():
                if axis in self._state.axes:
                    self._state.axes[axis] = float(value)
            self._state.last_error = None
            self._state.last_update_ts = time.time()
        return self.get_state()

    def clear_override(self) -> dict:
        self._check_resource_health()
        body = struct.pack("BB", TYPE_CLEAR, 0) + struct.pack("<" + "f" * len(AXES), *([0.0] * len(AXES)))
        crc = crc32_ieee(body)
        packet = body + struct.pack("<I", crc & 0xFFFFFFFF)
        self.sender.send(packet)
        with self._lock:
            self._state.active = False
            self._state.axes = {axis: 0.0 for axis in AXES}
            self._state.last_error = None
            self._state.last_update_ts = time.time()
        return self.get_state()

    def set_error(self, message: str) -> None:
        with self._lock:
            self._state.last_error = message
            self._state.last_update_ts = time.time()

    def get_state(self) -> dict:
        with self._lock:
            return {
                "active": self._state.active,
                "axes": dict(self._state.axes),
                "last_error": self._state.last_error,
                "last_update_ts": self._state.last_update_ts,
            }


def init_setpoint_override(
    host: str = DEFAULT_ROV_HOST, port: int = SETPOINT_OVERRIDE_PORT, resource_monitor=None
) -> SetpointOverrideClient:
    return SetpointOverrideClient(host=host, port=port, resource_monitor=resource_monitor)
