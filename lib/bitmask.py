# lib/bitmask.py
import socket, struct, threading, time, zlib
from dataclasses import dataclass, asdict

NUCLEO_HOST = "192.168.1.100" # default NUCLEO IP
NUCLEO_PORT = 12345
DEFAULT_RATE_HZ = 20.0      # send frequency

@dataclass
class Command:
    surge: int = 0    # [-128..127]
    sway: int = 0     # [-128..127]
    heave: int = 0    # [-128..127]
    roll: int = 0     # [-128..127]
    pitch: int = 0    # [-128..127]
    yaw: int = 0      # [-128..127]
    light: int = 0    # [0..255]
    manip: int = 0    # [-128..127]

def _i8(x: int) -> int:  return max(-128, min(127, int(x)))
def _u8(x: int) -> int:  return max(0, min(255, int(x)))
def _bias(i8: int) -> int: return (_i8(i8) + 128) & 0xFF

def encode_payload(cmd: Command) -> int:
    p = 0
    p |= (_bias(cmd.surge) & 0xFF) << 0
    p |= (_bias(cmd.sway)  & 0xFF) << 8
    p |= (_bias(cmd.heave) & 0xFF) << 16
    p |= (_bias(cmd.roll)  & 0xFF) << 24
    p |= (_bias(cmd.pitch) & 0xFF) << 32
    p |= (_bias(cmd.yaw)   & 0xFF) << 40
    p |= (_u8(cmd.light)   & 0xFF) << 48
    p |= (_bias(cmd.manip)   & 0xFF) << 56
    return p & 0xFFFFFFFFFFFFFFFF

def build_packet(seq: int, payload_u64: int) -> bytes:
    header = struct.pack("!IQ", seq & 0xFFFFFFFF, payload_u64 & 0xFFFFFFFFFFFFFFFF)
    crc = zlib.crc32(header) & 0xFFFFFFFF
    return header + struct.pack("!I", crc)

class BitmaskClient:
    def __init__(self, host=NUCLEO_HOST, port=NUCLEO_PORT, rate_hz=DEFAULT_RATE_HZ):
        self.host, self.port = host, port
        self.period = 1.0 / float(rate_hz) if rate_hz > 0 else 0.0
        self._cmd = Command()
        self._seq = 0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="BitmaskSender", daemon=True)
        self._sock = None

    def start(self):
        if self._thread.is_alive(): return
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread.is_alive(): self._thread.join(timeout=1.0)
        if self._sock:
            try: self._sock.close()
            except: pass
            self._sock = None

    def set_command(self, **kwargs):
        with self._lock:
            for k, v in kwargs.items():
                if hasattr(self._cmd, k):
                    setattr(self._cmd, k, int(v))

    def get_command(self) -> dict:
        with self._lock:
            return asdict(self._cmd) | {"sequence": self._seq}

    # convenience: set from normalized axes
    def set_from_axes(self, surge=0.0, sway=0.0, heave=0.0, roll=0.0, pitch=0.0, yaw=0.0,
                      light=0.0, manip=0.0):
        def s(x): return int(round(max(-1.0, min(1.0, float(x))) * 127))
        def u(x): return int(round(max(0.0, min(1.0, float(x))) * 255))
        self.set_command(surge=s(surge), sway=s(sway), heave=s(heave),
                         roll=s(roll), pitch=s(pitch), yaw=s(yaw),
                         light=u(light), manip=s(manip))

    def _run(self):
        if self.period <= 0: return
        while not self._stop.is_set():
            with self._lock:
                payload = encode_payload(self._cmd)
                pkt = build_packet(self._seq, payload)
                self._seq = (self._seq + 1) & 0xFFFFFFFF
            try:
                self._sock.sendto(pkt, (self.host, self.port))
            except Exception:
                pass
            time.sleep(self.period)

# simple initializer
def init_bitmask(rate_hz=DEFAULT_RATE_HZ, host=NUCLEO_HOST, port=NUCLEO_PORT) -> BitmaskClient:
    bm = BitmaskClient(host=host, port=port, rate_hz=rate_hz)
    bm.start()
    return bm
