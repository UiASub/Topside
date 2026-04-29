"""Reusable UDP transport helpers for all topside networking modules.

The ROV-side firmware exposes several UDP services (control, telemetry,
logging, resource monitoring, etc). Instead of letting every feature manage its
own sockets, this module centralizes the boilerplate: socket creation with
optional broadcast, listener-thread management, and convenience utilities such
as monotonically increasing sequence counters.
"""

from __future__ import annotations

import os
import socket
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

DEFAULT_ROV_HOST = os.getenv("ROV_HOST", "10.77.0.2")
DEFAULT_BROADCAST = os.getenv("ROV_BROADCAST", "10.77.0.255")
BUFFER_SIZE = 4096

Handler = Callable[[bytes, tuple[str, int]], None]


def next_sequence(prev: int) -> int:
    """Return *(prev + 1) mod 2**32*.

    The firmware's `net.c` expects 32-bit unsigned sequence numbers in big
    endian, so keeping the arithmetic centralized avoids subtle `& 0xFFFFFFFF`
    mistakes around the codebase.
    """

    return (prev + 1) & 0xFFFFFFFF


@dataclass
class UdpConfig:
    host: str = "0.0.0.0"
    port: int = 0
    broadcast: bool = False
    reuse: bool = True
    recv_buffer: int = BUFFER_SIZE
    timeout: float = 0.5  # seconds


class UdpSocket:
    """Thin wrapper that configures UDP sockets consistently."""

    def __init__(self, config: UdpConfig):
        self.config = config
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        if config.reuse:
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if config.broadcast:
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.sock.settimeout(config.timeout)
        if config.port:
            self.sock.bind((config.host, config.port))

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


class UdpListener:
    """Background listener that dispatches datagrams to a callback."""

    def __init__(self, name: str, config: UdpConfig, handler: Handler):
        self.name = name
        self.config = config
        self.handler = handler
        self.socket = UdpSocket(config)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name=name, daemon=True)

    def start(self) -> None:
        if not self._thread.is_alive():
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self.socket.close()

    def _run(self) -> None:
        sock = self.socket.sock
        while not self._stop.is_set():
            try:
                data, addr = sock.recvfrom(self.config.recv_buffer)
            except socket.timeout:
                continue
            except OSError as exc:
                if not self._stop.is_set():
                    print(f"[{self.name}] socket error: {exc}")
                    time.sleep(0.1)
                continue
            try:
                self.handler(data, addr)
            except Exception as exc:  # pylint: disable=broad-except
                print(f"[{self.name}] handler error: {exc}")


class UdpSender:
    """Shared UDP sender supporting broadcast overrides."""

    def __init__(self, host: str, port: int, broadcast: bool = False):
        cfg = UdpConfig(host="0.0.0.0", port=0, broadcast=broadcast, reuse=False)
        self.socket = UdpSocket(cfg)
        self.host = host
        self.port = port

    def send(self, payload: bytes, host: Optional[str] = None, port: Optional[int] = None) -> None:
        dest_host = host or self.host
        dest_port = port or self.port
        try:
            self.socket.sock.sendto(payload, (dest_host, dest_port))
        except OSError as exc:
            print(f"[UdpSender] send error to {dest_host}:{dest_port}: {exc}")

    def close(self) -> None:
        self.socket.close()


__all__ = [
    "DEFAULT_ROV_HOST",
    "DEFAULT_BROADCAST",
    "BUFFER_SIZE",
    "Handler",
    "next_sequence",
    "UdpConfig",
    "UdpSocket",
    "UdpListener",
    "UdpSender",
]
