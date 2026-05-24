"""Frame-control client for world-frame PID support."""

from __future__ import annotations

import struct
import threading
import time

from lib.crc import crc32_ieee
from lib.net_transport import DEFAULT_ROV_HOST, UdpSender

FRAME_CONTROL_PORT = 5009
FRAME_MAGIC = b"FRM1"
TYPE_LOCK = 0x01
TYPE_UNLOCK = 0x02


def build_frame_packet(command: int, sequence: int) -> bytes:
    body = FRAME_MAGIC + struct.pack("!B3xI", command, sequence & 0xFFFFFFFF)
    return body + struct.pack("!I", crc32_ieee(body))


class FrameControlClient:
    def __init__(self, host: str = DEFAULT_ROV_HOST, port: int = FRAME_CONTROL_PORT):
        self.host = host
        self.port = port
        self.sender = UdpSender(host, port)
        self._lock = threading.Lock()
        self._sequence = 0
        self._active = False
        self._last_update_ts = 0.0
        self._last_error: str | None = None

    def close(self) -> None:
        self.sender.close()

    def _send(self, command: int) -> dict:
        with self._lock:
            self._sequence = (self._sequence + 1) & 0xFFFFFFFF
            sequence = self._sequence
        self.sender.send(build_frame_packet(command, sequence))
        with self._lock:
            self._active = command == TYPE_LOCK
            self._last_update_ts = time.time()
            self._last_error = None
        return self.get_state()

    def lock(self) -> dict:
        return self._send(TYPE_LOCK)

    def unlock(self) -> dict:
        return self._send(TYPE_UNLOCK)

    def set_error(self, message: str) -> None:
        with self._lock:
            self._last_error = message
            self._last_update_ts = time.time()

    def get_state(self) -> dict:
        with self._lock:
            return {
                "active": self._active,
                "last_update_ts": self._last_update_ts,
                "last_error": self._last_error,
            }


def init_frame_control(host: str = DEFAULT_ROV_HOST, port: int = FRAME_CONTROL_PORT) -> FrameControlClient:
    return FrameControlClient(host=host, port=port)
