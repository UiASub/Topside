#!/usr/bin/env python3
"""
Resource Monitor - Topside Display
Receives and displays telemetry from the Nucleo board

Usage:
    python resource_monitor.py [--port PORT] [--nucleo-ip IP]

Example:
    python resource_monitor.py --port 12346 --nucleo-ip 192.168.1.100
"""

import socket
import struct
import argparse
import time
import sys
import os
from datetime import datetime

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
CRC32_TABLE = []

def init_crc32_table():
    """Initialize CRC32 lookup table"""
    global CRC32_TABLE
    for i in range(256):
        crc = i
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xEDB88320
            else:
                crc >>= 1
        CRC32_TABLE.append(crc)

def calculate_crc32(data: bytes) -> int:
    """Calculate CRC32 checksum matching the embedded implementation"""
    crc = 0xFFFFFFFF
    for byte in data:
        index = (crc ^ byte) & 0xFF
        crc = (crc >> 8) ^ CRC32_TABLE[index]
    return crc ^ 0xFFFFFFFF

def format_uptime(ms: int) -> str:
    """Format uptime in human-readable format"""
    seconds = ms // 1000
    minutes = seconds // 60
    hours = minutes // 60
    days = hours // 24

    if days > 0:
        return f"{days}d {hours%24:02d}:{minutes%60:02d}:{seconds%60:02d}"
    elif hours > 0:
        return f"{hours}:{minutes%60:02d}:{seconds%60:02d}"
    else:
        return f"{minutes}:{seconds%60:02d}"

def progress_bar(percent: int, width: int = 20) -> str:
    """Create a text-based progress bar"""
    filled = int(width * percent / 100)
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}]"

def clear_screen():
    """Clear the terminal screen"""
    os.system('cls' if os.name == 'nt' else 'clear')

def parse_telemetry(data: bytes) -> dict:
    """Parse telemetry packet and validate CRC"""
    if len(data) != TELEMETRY_SIZE:
        return None

    # Unpack the data
    (sequence, uptime_ms, cpu_percent, heap_used_percent,
     heap_free_kb, heap_total_kb, thread_count, reserved,
     udp_rx_count, udp_rx_errors, recv_crc) = struct.unpack(TELEMETRY_FORMAT, data)

    # Validate CRC (calculated over all fields except CRC itself)
    crc_data = data[:-4]  # Everything except the last 4 bytes (CRC)
    calculated_crc = calculate_crc32(crc_data)

    if calculated_crc != recv_crc:
        print(f"CRC mismatch! Expected: 0x{calculated_crc:08X}, Got: 0x{recv_crc:08X}")
        return None

    return {
        'sequence': sequence,
        'uptime_ms': uptime_ms,
        'cpu_percent': cpu_percent,
        'heap_used_percent': heap_used_percent,
        'heap_free_kb': heap_free_kb,
        'heap_total_kb': heap_total_kb,
        'thread_count': thread_count,
        'udp_rx_count': udp_rx_count,
        'udp_rx_errors': udp_rx_errors,
    }

def display_telemetry(telemetry: dict, last_seq: int):
    """Display telemetry in a formatted view"""
    clear_screen()

    print("╔════════════════════════════════════════════════════════════╗")
    print("║           NUCLEO RESOURCE MONITOR                          ║")
    print("╠════════════════════════════════════════════════════════════╣")
    print(f"║  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}                              ║")
    print(f"║  Uptime: {format_uptime(telemetry['uptime_ms']):>15}                          ║")
    print(f"║  Sequence: {telemetry['sequence']:>10}                               ║")

    # Packet loss detection
    if last_seq >= 0:
        expected = last_seq + 1
        if telemetry['sequence'] != expected and telemetry['sequence'] != 0:
            lost = telemetry['sequence'] - expected
            if lost > 0:
                print(f"║  ⚠ Packets lost: {lost}                                    ║")

    print("╠════════════════════════════════════════════════════════════╣")
    print("║  CPU USAGE                                                 ║")
    cpu = telemetry['cpu_percent']
    cpu_bar = progress_bar(cpu)
    cpu_color = "🟢" if cpu < 50 else "🟡" if cpu < 80 else "🔴"
    print(f"║  {cpu_color} {cpu_bar} {cpu:3d}%                          ║")

    print("╠════════════════════════════════════════════════════════════╣")
    print("║  MEMORY                                                    ║")
    heap_used = telemetry['heap_used_percent']
    heap_bar = progress_bar(heap_used)
    heap_color = "🟢" if heap_used < 50 else "🟡" if heap_used < 80 else "🔴"
    print(f"║  {heap_color} {heap_bar} {heap_used:3d}%                          ║")
    print(f"║     Free: {telemetry['heap_free_kb']:>5} KB / Total: {telemetry['heap_total_kb']:>5} KB            ║")

    print("╠════════════════════════════════════════════════════════════╣")
    print("║  THREADS                                                   ║")
    print(f"║     Active threads: {telemetry['thread_count']:>3}                                ║")

    print("╠════════════════════════════════════════════════════════════╣")
    print("║  NETWORK                                                   ║")
    print(f"║     UDP packets received: {telemetry['udp_rx_count']:>10}                    ║")
    print(f"║     UDP errors:           {telemetry['udp_rx_errors']:>10}                    ║")

    print("╠════════════════════════════════════════════════════════════╣")
    print("║  Press Ctrl+C to exit                                      ║")
    print("╚════════════════════════════════════════════════════════════╝")

def main():
    parser = argparse.ArgumentParser(description='Nucleo Resource Monitor - Topside Display')
    parser.add_argument('--port', type=int, default=12346,
                        help='UDP port to listen on (default: 12346)')
    parser.add_argument('--nucleo-ip', type=str, default='192.168.1.100',
                        help='Nucleo board IP address (default: 192.168.1.100)')
    parser.add_argument('--bind-ip', type=str, default='0.0.0.0',
                        help='IP address to bind to (default: 0.0.0.0)')
    args = parser.parse_args()

    # Initialize CRC table
    init_crc32_table()

    # Create UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        sock.bind((args.bind_ip, args.port))
    except OSError as e:
        print(f"Error binding to {args.bind_ip}:{args.port}: {e}")
        sys.exit(1)

    print(f"Listening for telemetry on {args.bind_ip}:{args.port}")
    print(f"Expecting data from Nucleo at {args.nucleo_ip}")
    print("Waiting for first packet...")

    last_sequence = -1
    packet_count = 0

    try:
        while True:
            # Receive telemetry packet
            data, addr = sock.recvfrom(1024)

            # Parse the telemetry
            telemetry = parse_telemetry(data)

            if telemetry:
                packet_count += 1
                display_telemetry(telemetry, last_sequence)
                last_sequence = telemetry['sequence']
            else:
                print(f"Invalid packet received from {addr}, size: {len(data)}")

    except KeyboardInterrupt:
        print("\n\nMonitor stopped.")
        print(f"Total packets received: {packet_count}")
    finally:
        sock.close()

if __name__ == '__main__':
    main()
