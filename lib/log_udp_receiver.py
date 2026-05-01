"""Listener for Zephyr's UDP log backend.

The firmware forwards human-readable log lines over UDP broadcast on
``LOG_UDP_PORT`` (5006). Each datagram is a newline-terminated chunk; there is
no reply/acknowledgement channel. This module buffers the most recent entries so
the debug page can show live logs while also writing everything to disk for
post-mission correlation.
"""

from __future__ import annotations

import json
import re
import threading
import time
from typing import List

from lib.net_transport import UdpConfig, UdpListener
from lib.runtime_paths import log_path, logs_dir

LOG_PORT = 5006
LOG_DIR = logs_dir()
LOG_FILE = log_path("zephyr.log")
SEVERITY_RE = re.compile(r"^\[(?P<level>[IWRD])\]\s*")


class LogStreamReceiver:
    def __init__(self, host: str = "0.0.0.0", port: int = LOG_PORT, max_entries: int = 500):
        self.host = host
        self.port = port
        self.max_entries = max_entries
        self._listener: UdpListener | None = None
        self._buffer: List[dict] = []
        self._lock = threading.Lock()
        LOG_DIR.mkdir(parents=True, exist_ok=True)

    def start(self) -> None:
        if self._listener is not None:
            return
        cfg = UdpConfig(host=self.host, port=self.port, broadcast=True, timeout=1.0, recv_buffer=2048)
        self._listener = UdpListener("LogStream", cfg, self._handle_packet)
        self._listener.start()
        print(f"Log stream receiver listening on {self.host}:{self.port}")

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()
            self._listener = None
        print("Log stream receiver stopped")

    def get_recent(self, limit: int = 100) -> List[dict]:
        with self._lock:
            return list(self._buffer[-limit:])

    def _handle_packet(self, data: bytes, addr: tuple[str, int]):
        try:
            text = data.decode("utf-8", errors="replace").rstrip("\r\n")
        except Exception as exc:
            print(f"Log stream: decode error from {addr}: {exc}")
            return
        level = "I"
        match = SEVERITY_RE.match(text)
        if match:
            level = match.group("level")
            text = text[match.end() :]
        entry = {
            "ts": time.time(),
            "level": level,
            "message": text,
        }
        with self._lock:
            self._buffer.append(entry)
            if len(self._buffer) > self.max_entries:
                self._buffer = self._buffer[-self.max_entries :]
        self._append_log(entry)

    def _append_log(self, entry: dict) -> None:
        try:
            with LOG_FILE.open("a", encoding="utf-8") as fp:
                fp.write(json.dumps(entry) + "\n")
        except OSError as exc:
            print(f"Log stream: failed to write log: {exc}")


def init_log_stream(host: str = "0.0.0.0", port: int = LOG_PORT) -> LogStreamReceiver:
    receiver = LogStreamReceiver(host=host, port=port)
    receiver.start()
    return receiver
