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
LEGACY_SEVERITY_RE = re.compile(r"^\[(?P<level>[IWERD])\]\s*")
ZEPHYR_SEVERITY_RE = re.compile(r"<(?P<level>inf|wrn|err|dbg)>")
LEVEL_MAP = {
    "I": "I",
    "W": "W",
    "E": "E",
    "R": "E",
    "D": "D",
    "inf": "I",
    "wrn": "W",
    "err": "E",
    "dbg": "D",
}


class LogStreamReceiver:
    def __init__(self, host: str = "0.0.0.0", port: int = LOG_PORT, max_entries: int = 500):
        self.host = host
        self.port = port
        self.max_entries = max_entries
        self._listener: UdpListener | None = None
        self._buffer: List[dict] = []
        self._lock = threading.Lock()
        self._packet_count = 0
        self._decode_errors = 0
        self._last_ts = None
        self._last_addr = None
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

    def get_stats(self) -> dict:
        with self._lock:
            age_ms = None if self._last_ts is None else max(0.0, (time.time() - self._last_ts) * 1000.0)
            return {
                "packet_count": self._packet_count,
                "decode_errors": self._decode_errors,
                "last_age_ms": age_ms,
                "last_addr": list(self._last_addr) if self._last_addr else None,
                "log_file": str(LOG_FILE),
            }

    def _handle_packet(self, data: bytes, addr: tuple[str, int]):
        try:
            text = data.decode("utf-8", errors="replace").rstrip("\r\n")
        except Exception as exc:
            with self._lock:
                self._decode_errors += 1
            print(f"Log stream: decode error from {addr}: {exc}")
            return
        now = time.time()
        entries = []
        for line in (part for part in text.splitlines() if part.strip()):
            entries.append(self._build_entry(line, now))
        if not entries:
            return
        with self._lock:
            self._packet_count += 1
            self._last_ts = now
            self._last_addr = addr
            self._buffer.extend(entries)
            if len(self._buffer) > self.max_entries:
                self._buffer = self._buffer[-self.max_entries :]
        for entry in entries:
            self._append_log(entry)

    def _build_entry(self, text: str, now: float) -> dict:
        level = "I"
        legacy = LEGACY_SEVERITY_RE.match(text)
        if legacy:
            level = LEVEL_MAP.get(legacy.group("level"), "I")
            text = text[legacy.end() :]
        else:
            zephyr = ZEPHYR_SEVERITY_RE.search(text)
            if zephyr:
                level = LEVEL_MAP.get(zephyr.group("level"), "I")
        return {
            "ts": now,
            "level": level,
            "message": text.strip(),
        }

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
