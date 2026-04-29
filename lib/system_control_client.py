"""Send system-level control commands to the MCU."""

import struct
import time

from lib.crc import crc32_ieee
from lib.net_transport import DEFAULT_ROV_HOST, UdpSender, next_sequence

SYSTEM_CONTROL_PORT = 5008
RESET_MAGIC = b"RST1"


def build_reset_packet(sequence: int) -> bytes:
    body = RESET_MAGIC + struct.pack("!I", sequence & 0xFFFFFFFF)
    crc = crc32_ieee(body)
    return body + struct.pack("!I", crc)


class SystemControlClient:
    def __init__(self, host=DEFAULT_ROV_HOST, port=SYSTEM_CONTROL_PORT):
        self.host = host
        self.port = port
        self._sender = UdpSender(host, port)
        self._sequence = 0
        self._last_reset_time = None

    def close(self) -> None:
        self._sender.close()

    def send_reset(self, repeats: int = 3, delay: float = 0.05) -> dict:
        sequence = self._sequence
        packet = build_reset_packet(sequence)
        for _ in range(max(1, repeats)):
            self._sender.send(packet)
            if delay > 0:
                time.sleep(delay)
        self._sequence = next_sequence(self._sequence)
        self._last_reset_time = time.time()
        return {
            "sequence": sequence,
            "host": self.host,
            "port": self.port,
            "repeats": max(1, repeats),
            "last_reset_time": self._last_reset_time,
        }
