"""
Resource Monitor Receiver - UDP telemetry from Nucleo board

Receives telemetry packets containing CPU usage, memory stats, thread count,
and network statistics. Packet format matches resource_monitor.h on the Nucleo.
"""

import socket
import struct
import threading
import time
from lib.json_data_handler import JSONDataHandler

UDP_IP = "0.0.0.0"
UDP_PORT = 12346

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

# CRC32 lookup table (IEEE 802.3 polynomial)
CRC32_TABLE = None


def _init_crc32_table():
    """Initialize CRC32 lookup table."""
    global CRC32_TABLE
    if CRC32_TABLE is not None:
        return
    CRC32_TABLE = []
    for i in range(256):
        crc = i
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xEDB88320
            else:
                crc >>= 1
        CRC32_TABLE.append(crc)


def _calculate_crc32(data: bytes) -> int:
    """Calculate CRC32 checksum matching the embedded implementation."""
    if CRC32_TABLE is None:
        _init_crc32_table()
    crc = 0xFFFFFFFF
    for byte in data:
        index = (crc ^ byte) & 0xFF
        crc = (crc >> 8) ^ CRC32_TABLE[index]
    return crc ^ 0xFFFFFFFF


class ResourceReceiver:
    """Background UDP receiver for resource telemetry from Nucleo board."""

    def __init__(self, host=UDP_IP, port=UDP_PORT, data_handler=None):
        self.host = host
        self.port = port
        self.data_handler = data_handler or JSONDataHandler()

        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="ResourceReceiver", daemon=True)
        self._sock = None

        # Stats
        self._lock = threading.Lock()
        self._packet_count = 0
        self._crc_errors = 0
        self._last_seq = None
        self._packets_lost = 0
        self._last_data = {}

        # Initialize CRC table
        _init_crc32_table()

    def start(self):
        """Start the receiver thread."""
        if self._thread.is_alive():
            return
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self.host, self.port))
        self._sock.settimeout(1.0)  # Allow periodic stop checks
        self._thread.start()
        print(f"Resource receiver started on {self.host}:{self.port}")

    def stop(self):
        """Stop the receiver thread."""
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=2.0)
        if self._sock:
            try:
                self._sock.close()
            except:
                pass
            self._sock = None
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

    def _run(self):
        """Main receiver loop."""
        while not self._stop.is_set():
            try:
                data, addr = self._sock.recvfrom(1024)
                self._process_packet(data, addr)
            except socket.timeout:
                # Normal timeout, check stop flag
                continue
            except Exception as e:
                if not self._stop.is_set():
                    print(f"Resource receiver error: {e}")
                time.sleep(0.1)

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
        calculated_crc = _calculate_crc32(crc_data)

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


def init_resource_receiver(host=UDP_IP, port=UDP_PORT, data_handler=None) -> ResourceReceiver:
    """Initialize and start the resource receiver."""
    receiver = ResourceReceiver(host=host, port=port, data_handler=data_handler)
    receiver.start()
    return receiver
