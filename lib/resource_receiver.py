from __future__ import annotations

"""Resource monitor telemetry receiver.

Decodes the packed ``telemetry_packet_t`` struct described in
``resource_monitor.h`` and keeps ``data/data.json`` updated with the latest
statistics so the web UI can present CPU, memory, and UDP health dashboards.

Each packet is big-endian with an IEEE 802.3 CRC appended. This module shares
the global CRC helper plus the UDP transport scaffolding so that the receiver
matches the embedded ``crc32_calc()`` and ``net.c`` behavior exactly.
"""

import json
import struct
import threading
import time
from pathlib import Path

from lib.crc import crc32_ieee
from lib.json_data_handler import JSONDataHandler
from lib.net_transport import UdpConfig, UdpListener

UDP_IP = "0.0.0.0"
UDP_PORT = 12346
LOG_DIR = Path("logs")
RESOURCE_LOG = LOG_DIR / "resource_monitor.ndjson"
DIAG_LOG_EVERY_SEC = 5.0

# Telemetry packet format (must match resource_monitor.h)
# typedef struct {
#     uint32_t sequence;          /* Packet sequence number */
#     uint32_t uptime_ms;         /* System uptime in milliseconds */
#     uint8_t  cpu_usage_percent; /* CPU usage 0-100% */
#     uint8_t  heap_used_percent; /* Heap memory used 0-100% */
#     uint16_t heap_free_kb;      /* Free heap in KB */
#     uint16_t heap_total_kb;     /* Total heap in KB */
#     uint8_t  thread_count;      /* Number of active threads */
#     uint8_t  reserved;          /* Padding for alignment */
#     uint32_t udp_rx_count;      /* UDP packets received */
#     uint32_t udp_rx_errors;     /* UDP receive errors */
#     uint32_t crc32;             /* CRC32 checksum */
# } __attribute__((packed)) telemetry_packet_t;

TELEMETRY_FORMAT = ">IIBBHHBBIII"  # Big-endian (network byte order)
TELEMETRY_SIZE = struct.calcsize(TELEMETRY_FORMAT)

class ResourceReceiver:
    """Background UDP receiver for resource telemetry from Nucleo board."""

    def __init__(self, host=UDP_IP, port=UDP_PORT, data_handler=None):
        self.host = host
        self.port = port
        self.data_handler = data_handler or JSONDataHandler()

        self._stop = threading.Event()
        self._listener: UdpListener | None = None

        # Stats
        self._lock = threading.Lock()
        self._packet_count = 0
        self._crc_errors = 0
        self._last_seq = None
        self._packets_lost = 0
        self._last_data = {}

        self._last_diag_log = 0.0
        LOG_DIR.mkdir(parents=True, exist_ok=True)

    def start(self):
        """Start the receiver thread."""
        if self._listener is not None:
            return
        cfg = UdpConfig(host=self.host, port=self.port, broadcast=False, timeout=1.0, recv_buffer=1024)
        self._listener = UdpListener("ResourceReceiver", cfg, self._process_packet)
        self._stop.clear()
        self._listener.start()
        print(f"Resource receiver started on {self.host}:{self.port}")

    def stop(self):
        """Stop the receiver thread."""
        self._stop.set()
        if self._listener:
            self._listener.stop()
            self._listener = None
        print("Resource receiver stopped")

    def get_stats(self) -> dict:
        """Get receiver statistics."""
        with self._lock:
            return {
                "packet_count": self._packet_count,
                "crc_errors": self._crc_errors,
                "packets_lost": self._packets_lost,
                "last_seq": self._last_seq,
                "last_data": self._last_data.copy()
            }

    def _process_packet(self, data: bytes, addr: tuple):
        """Process incoming UDP telemetry packet."""
        if len(data) != TELEMETRY_SIZE:
            print(f"Resource: Invalid packet size from {addr}: {len(data)} (expected {TELEMETRY_SIZE})")
            return

        # Unpack the data
        try:
            (sequence, uptime_ms, cpu_percent, heap_used_percent,
             heap_free_kb, heap_total_kb, thread_count, reserved,
             udp_rx_count, udp_rx_errors, recv_crc) = struct.unpack(TELEMETRY_FORMAT, data)
        except struct.error as e:
            print(f"Resource: Unpack error from {addr}: {e}")
            return

        # Validate CRC (calculated over all fields except CRC itself)
        crc_data = data[:-4]  # Everything except the last 4 bytes (CRC)
        calculated_crc = crc32_ieee(crc_data)

        if calculated_crc != recv_crc:
            with self._lock:
                self._crc_errors += 1
            print(f"Resource: CRC mismatch! Expected: 0x{calculated_crc:08X}, Got: 0x{recv_crc:08X}")
            return

        # Build telemetry dict
        telemetry = {
            "sequence": sequence,
            "uptime_ms": uptime_ms,
            "cpu_percent": cpu_percent,
            "heap_used_percent": heap_used_percent,
            "heap_free_kb": heap_free_kb,
            "heap_total_kb": heap_total_kb,
            "thread_count": thread_count,
            "udp_rx_count": udp_rx_count,
            "udp_rx_errors": udp_rx_errors
        }

        # Update stats
        with self._lock:
            self._packet_count += 1

            # Check for packet loss
            if self._last_seq is not None:
                expected = (self._last_seq + 1) & 0xFFFFFFFF
                if sequence != expected and sequence != 0:
                    lost = sequence - expected
                    if lost > 0:
                        self._packets_lost += lost
                        print(f"Resource: Packet loss detected, {lost} packets lost")

            self._last_seq = sequence
            self._last_data = telemetry.copy()

        # Update data.json with new resource values
        try:
            self.data_handler.update_data({"resources": telemetry})
        except Exception as e:
            print(f"Resource: Error updating data: {e}")

        self._maybe_log_diag(telemetry)

    def _maybe_log_diag(self, telemetry: dict) -> None:
        now = time.monotonic()
        if now - self._last_diag_log < DIAG_LOG_EVERY_SEC:
            return
        self._last_diag_log = now
        record = telemetry | {
            "packets": self._packet_count,
            "crc_errors": self._crc_errors,
            "packets_lost": self._packets_lost,
            "timestamp": time.time(),
        }
        try:
            with RESOURCE_LOG.open("a", encoding="utf-8") as fp:
                fp.write(json.dumps(record) + "\n")
        except OSError as exc:
            print(f"Resource: failed to log telemetry: {exc}")

    def get_udp_counters(self) -> tuple[int, int]:
        with self._lock:
            last = self._last_data or {}
            return last.get("udp_rx_count", 0), last.get("udp_rx_errors", 0)


def init_resource_receiver(host=UDP_IP, port=UDP_PORT, data_handler=None) -> ResourceReceiver:
    """Initialize and start the resource receiver."""
    receiver = ResourceReceiver(host=host, port=port, data_handler=data_handler)
    receiver.start()
    return receiver
