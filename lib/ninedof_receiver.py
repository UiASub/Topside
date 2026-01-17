import socket
import json
import threading
import time
from lib.json_data_handler import JSONDataHandler

UDP_IP = "0.0.0.0"
UDP_PORT = 5002

# ICM20948 config:
# accel: +/-2g  => 16384 LSB/g
# gyro:  +/-250 => 131   LSB/(dps)
ACC_LSB_PER_G = 16384.0
GYRO_LSB_PER_DPS = 131.0


class NineDOFReceiver:
    """Background UDP receiver for 9DOF sensor data from Nucleo board."""

    def __init__(self, host=UDP_IP, port=UDP_PORT, data_handler=None):
        self.host = host
        self.port = port
        self.data_handler = data_handler or JSONDataHandler()

        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="9DOFReceiver", daemon=True)
        self._sock = None

        # Stats
        self._lock = threading.Lock()
        self._packet_count = 0
        self._last_seq = None
        self._last_data = {}

    def start(self):
        """Start the receiver thread."""
        if self._thread.is_alive():
            return
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self.host, self.port))
        self._sock.settimeout(1.0)  # Allow periodic stop checks
        self._thread.start()
        print(f"9DOF receiver started on {self.host}:{self.port}")

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
        print("9DOF receiver stopped")

    def get_stats(self) -> dict:
        """Get receiver statistics."""
        with self._lock:
            return {
                "packet_count": self._packet_count,
                "last_seq": self._last_seq,
                "last_data": self._last_data.copy()
            }

    def _run(self):
        """Main receiver loop."""
        while not self._stop.is_set():
            try:
                data, addr = self._sock.recvfrom(2048)
                self._process_packet(data, addr)
            except socket.timeout:
                # Normal timeout, check stop flag
                continue
            except Exception as e:
                if not self._stop.is_set():
                    print(f"9DOF receiver error: {e}")
                time.sleep(0.1)

    def _process_packet(self, data: bytes, addr: tuple):
        """Process incoming UDP packet with 9DOF data."""
        try:
            msg = json.loads(data.decode("utf-8", errors="strict"))
        except Exception as e:
            print(f"9DOF: Bad JSON from {addr}: {e}")
            return

        seq = msg.get("seq")
        t_ms = msg.get("t_ms")
        nine = msg.get("9dof", {})

        accel_raw = nine.get("accel", [0, 0, 0])
        gyro_raw = nine.get("gyro", [0, 0, 0])

        # Convert to physical units
        accel_g = {
            "x": round(accel_raw[0] / ACC_LSB_PER_G, 4),
            "y": round(accel_raw[1] / ACC_LSB_PER_G, 4),
            "z": round(accel_raw[2] / ACC_LSB_PER_G, 4)
        }
        gyro_dps = {
            "x": round(gyro_raw[0] / GYRO_LSB_PER_DPS, 2),
            "y": round(gyro_raw[1] / GYRO_LSB_PER_DPS, 2),
            "z": round(gyro_raw[2] / GYRO_LSB_PER_DPS, 2)
        }

        # Update stats
        with self._lock:
            self._packet_count += 1
            # Check for packet loss
            if isinstance(seq, int) and self._last_seq is not None:
                if seq != (self._last_seq + 1) % (2**32):
                    print(f"9DOF: Sequence jump {self._last_seq} -> {seq}")
            self._last_seq = seq
            self._last_data = {
                "seq": seq,
                "t_ms": t_ms,
                "acceleration": accel_g,
                "gyroscope": gyro_dps
            }

        # Update data.json with new sensor values
        try:
            self.data_handler.update_data({
                "9dof": {
                    "acceleration": accel_g,
                    "gyroscope": gyro_dps,
                    "magnetometer": self.data_handler.get_section("9dof").get(
                        "magnetometer", {"x": 0, "y": 0, "z": 0}
                    )
                }
            })
        except Exception as e:
            print(f"9DOF: Error updating data: {e}")


def init_ninedof_receiver(host=UDP_IP, port=UDP_PORT, data_handler=None) -> NineDOFReceiver:
    """Initialize and start the 9DOF receiver."""
    receiver = NineDOFReceiver(host=host, port=port, data_handler=data_handler)
    receiver.start()
    return receiver
