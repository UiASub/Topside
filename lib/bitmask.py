# lib/bitmask.py
import struct
import threading
import time
from dataclasses import asdict, dataclass
from typing import Optional

from lib.crc import crc32_ieee
from lib.net_transport import DEFAULT_ROV_HOST, UdpSender, next_sequence

NUCLEO_HOST = DEFAULT_ROV_HOST  # default NUCLEO IP
NUCLEO_PORT = 12345
DEFAULT_RATE_HZ = 20.0  # send frequency


@dataclass
class Command:
    surge: int = 0  # [-128..127]
    sway: int = 0  # [-128..127]
    heave: int = 0  # [-128..127]
    roll: int = 0  # [-128..127]
    pitch: int = 0  # [-128..127]
    yaw: int = 0  # [-128..127]
    light: int = 0  # [0..255]
    manip: int = 0  # [-128..127]


def _i8(x: int) -> int:
    return max(-128, min(127, int(x)))


def _u8(x: int) -> int:
    return max(0, min(255, int(x)))


def _bias(i8: int) -> int:
    return (_i8(i8) + 128) & 0xFF


def encode_payload(cmd: Command) -> int:
    p = 0
    p |= (_bias(cmd.surge) & 0xFF) << 0
    p |= (_bias(cmd.sway) & 0xFF) << 8
    p |= (_bias(cmd.heave) & 0xFF) << 16
    p |= (_bias(cmd.roll) & 0xFF) << 24
    p |= (_bias(cmd.pitch) & 0xFF) << 32
    p |= (_bias(cmd.yaw) & 0xFF) << 40
    p |= (_u8(cmd.light) & 0xFF) << 48
    p |= (_bias(cmd.manip) & 0xFF) << 56
    return p & 0xFFFFFFFFFFFFFFFF


def build_packet(seq: int, payload_u64: int) -> bytes:
    header = struct.pack("!IQ", seq & 0xFFFFFFFF, payload_u64 & 0xFFFFFFFFFFFFFFFF)
    crc = crc32_ieee(header)
    return header + struct.pack("!I", crc & 0xFFFFFFFF)


class BitmaskClient:
    def __init__(self, host=NUCLEO_HOST, port=NUCLEO_PORT, rate_hz=DEFAULT_RATE_HZ, watchdog_timeout=0.75):
        self.host, self.port = host, port
        self.period = 1.0 / float(rate_hz) if rate_hz > 0 else 0.0
        self._cmd = Command()
        self._seq = 0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="BitmaskSender", daemon=True)
        self._watchdog_thread = threading.Thread(target=self._watchdog_loop, name="BitmaskWatchdog", daemon=True)
        self._sender: Optional[UdpSender] = None
        self._resource_monitor = None

        # Uplink health/state
        self._status_lock = threading.Lock()
        self._last_packet: bytes | None = None
        self._last_send_time = 0.0
        self._last_ack_time = 0.0
        self._last_ack_count = None
        self._watchdog_timeout = watchdog_timeout
        self._watchdog_resends = 0
        self._last_watchdog_resend_time = 0.0
        self._last_command_snapshot: dict | None = None

    def start(self):
        if self._thread.is_alive():
            return
        self._sender = UdpSender(self.host, self.port)
        self._stop.clear()
        with self._status_lock:
            self._last_ack_time = 0.0
            self._last_ack_count = None
        self._thread.start()
        self._watchdog_thread.start()

    def stop(self):
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=1.0)
        if self._watchdog_thread.is_alive():
            self._watchdog_thread.join(timeout=1.0)
        if self._sender:
            self._sender.close()
            self._sender = None

    def set_command(self, **kwargs):
        with self._lock:
            for k, v in kwargs.items():
                if hasattr(self._cmd, k):
                    setattr(self._cmd, k, int(v))

    def get_command(self) -> dict:
        with self._lock:
            return asdict(self._cmd) | {"sequence": self._seq}

    def set_resource_monitor(self, monitor) -> None:
        self._resource_monitor = monitor

    def get_uplink_status(self) -> dict:
        with self._status_lock:
            now = time.monotonic()
            send_age = None if self._last_send_time == 0 else max(0.0, now - self._last_send_time) * 1000.0
            ack_age = None if self._last_ack_time == 0 else max(0.0, now - self._last_ack_time) * 1000.0
            resend_age = (
                None
                if self._last_watchdog_resend_time == 0
                else max(0.0, now - self._last_watchdog_resend_time) * 1000.0
            )
            return {
                "sequence": self._seq,
                "last_send_age_ms": send_age,
                "last_send_timestamp": None if self._last_send_time == 0 else self._last_send_time,
                "last_ack_age_ms": ack_age,
                "last_ack_count": self._last_ack_count,
                "watchdog_timeout": self._watchdog_timeout,
                "watchdog_resends": self._watchdog_resends,
                "last_watchdog_resend_age_ms": resend_age,
                "last_command": self._last_command_snapshot or {},
                "last_packet_hex": self._last_packet.hex() if self._last_packet else None,
            }

    # convenience: set from normalized axes
    def set_from_axes(self, surge=0.0, sway=0.0, heave=0.0, roll=0.0, pitch=0.0, yaw=0.0, light=0.0, manip=0.0):
        def s(x):
            return int(round(max(-1.0, min(1.0, float(x))) * 127))

        def u(x):
            return int(round(max(0.0, min(1.0, float(x))) * 255))

        self.set_command(
            surge=s(surge),
            sway=s(sway),
            heave=s(heave),
            roll=s(roll),
            pitch=s(pitch),
            yaw=s(yaw),
            light=u(light),
            manip=s(manip),
        )

    def _run(self):
        if self.period <= 0:
            return
        while not self._stop.is_set():
            with self._lock:
                payload = encode_payload(self._cmd)
                pkt = build_packet(self._seq, payload)
                self._seq = next_sequence(self._seq)
                command_snapshot = asdict(self._cmd)
            sender = self._sender
            if sender:
                try:
                    sender.send(pkt)
                except Exception:
                    pass
            with self._status_lock:
                self._last_packet = pkt
                self._last_send_time = time.monotonic()
                self._last_command_snapshot = command_snapshot
            time.sleep(self.period)

    def _watchdog_loop(self):
        while not self._stop.is_set():
            time.sleep(0.1)
            monitor = self._resource_monitor
            if monitor is None:
                continue
            counters = getattr(monitor, "get_udp_counters", None)
            if counters is None:
                continue
            udp_rx_count, _errors = counters()
            now = time.monotonic()
            with self._status_lock:
                if self._last_ack_count is None:
                    self._last_ack_count = udp_rx_count
                    continue
                if udp_rx_count != self._last_ack_count:
                    self._last_ack_count = udp_rx_count
                    self._last_ack_time = now
                    continue
                # No new acks yet
                resend_due = (now - self._last_watchdog_resend_time) > self._watchdog_timeout
                if self._last_packet and (now - self._last_ack_time) > self._watchdog_timeout and resend_due:
                    sender = self._sender
                    if sender:
                        try:
                            sender.send(self._last_packet)
                            self._watchdog_resends += 1
                            self._last_watchdog_resend_time = now
                        except Exception:
                            pass


# simple initializer
def init_bitmask(rate_hz=DEFAULT_RATE_HZ, host=NUCLEO_HOST, port=NUCLEO_PORT) -> BitmaskClient:
    bm = BitmaskClient(host=host, port=port, rate_hz=rate_hz)
    bm.start()
    return bm
