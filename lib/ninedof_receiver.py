import socket
import json
import threading
import time
from lib.json_data_handler import JSONDataHandler

UDP_IP = "0.0.0.0"
UDP_PORT = 5002

# Default: identity mapping (sensor yaw/pitch/roll = ROV yaw/pitch/roll)
DEFAULT_AXES = {"yaw": "+yaw", "pitch": "+pitch", "roll": "+roll"}


def _build_remap(axes_cfg):
    """Build a remap dict from axis config.

    Each ROV output (yaw/pitch/roll) maps to a sensor output with an optional
    sign flip.  e.g. {"yaw": "-pitch", "pitch": "+yaw", "roll": "+roll"}
    means ROV yaw reads from inverted sensor pitch, etc.
    """
    remap = {}
    for key in ("yaw", "pitch", "roll"):
        val = axes_cfg.get(key, "+" + key)
        sign = -1.0 if val.startswith("-") else 1.0
        src = val.lstrip("+-")
        if src not in ("yaw", "pitch", "roll"):
            src = key
            sign = 1.0
        remap[key] = {"src": src, "sign": sign}
    return remap


class IMUReceiver:
    """Background UDP receiver for VN-100S IMU data (yaw/pitch/roll) from Nucleo board."""

    def __init__(self, host=UDP_IP, port=UDP_PORT, data_handler=None):
        self.host = host
        self.port = port
        self.data_handler = data_handler or JSONDataHandler()

        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="IMUReceiver", daemon=True)
        self._sock = None

        # Stats
        self._lock = threading.Lock()
        self._packet_count = 0
        self._last_data = {}
        self._last_recv_time = None

        # Tare offset (applied on topside to displayed values)
        self._tare_offset = {"yaw": 0.0, "pitch": 0.0, "roll": 0.0}

        # Axis remap (identity by default)
        self._remap = _build_remap(DEFAULT_AXES)

    def set_axis_mapping(self, axes_cfg):
        """Update axis mapping at runtime."""
        with self._lock:
            self._remap = _build_remap(axes_cfg)
        print(f"IMU axis mapping updated: {axes_cfg}")

    def start(self):
        """Start the receiver thread."""
        if self._thread.is_alive():
            return
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self.host, self.port))
        self._sock.settimeout(1.0)
        self._thread.start()
        print(f"IMU receiver started on {self.host}:{self.port}")

    def stop(self):
        """Stop the receiver thread."""
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=2.0)
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
        print("IMU receiver stopped")

    def tare(self):
        """Set current orientation as zero reference."""
        with self._lock:
            raw = self._last_data.get("raw", {})
            self._tare_offset = {
                "yaw": raw.get("yaw", 0.0),
                "pitch": raw.get("pitch", 0.0),
                "roll": raw.get("roll", 0.0),
            }

    def clear_tare(self):
        """Remove tare offset."""
        with self._lock:
            self._tare_offset = {"yaw": 0.0, "pitch": 0.0, "roll": 0.0}

    def get_stats(self) -> dict:
        """Get receiver statistics."""
        with self._lock:
            age_ms = None
            if self._last_recv_time is not None:
                age_ms = round((time.monotonic() - self._last_recv_time) * 1000)
            return {
                "packet_count": self._packet_count,
                "last_data": self._last_data.copy(),
                "age_ms": age_ms,
                "tare_offset": self._tare_offset.copy(),
            }

    def _apply_remap(self, sensor_yaw, sensor_pitch, sensor_roll):
        """Remap sensor yaw/pitch/roll to ROV frame based on axis config."""
        sensor_vals = {"yaw": sensor_yaw, "pitch": sensor_pitch, "roll": sensor_roll}
        remap = self._remap
        return (
            sensor_vals[remap["yaw"]["src"]] * remap["yaw"]["sign"],
            sensor_vals[remap["pitch"]["src"]] * remap["pitch"]["sign"],
            sensor_vals[remap["roll"]["src"]] * remap["roll"]["sign"],
        )

    def _run(self):
        """Main receiver loop."""
        while not self._stop.is_set():
            try:
                data, addr = self._sock.recvfrom(2048)
                self._process_packet(data, addr)
            except socket.timeout:
                continue
            except Exception as e:
                if not self._stop.is_set():
                    print(f"IMU receiver error: {e}")
                time.sleep(0.1)

    def _process_packet(self, data: bytes, addr: tuple):
        """Process incoming UDP packet with IMU data."""
        try:
            msg = json.loads(data.decode("utf-8", errors="strict"))
        except Exception as e:
            print(f"IMU: Bad JSON from {addr}: {e}")
            return

        imu = msg.get("imu", {})
        sensor_yaw = imu.get("yaw", 0.0)
        sensor_pitch = imu.get("pitch", 0.0)
        sensor_roll = imu.get("roll", 0.0)

        # Angular rates (deg/s) — same remap applies
        sensor_yr = imu.get("yr", 0.0)
        sensor_pr = imu.get("pr", 0.0)
        sensor_rr = imu.get("rr", 0.0)

        # Linear acceleration (m/s^2)
        accel_x = imu.get("ax", 0.0)
        accel_y = imu.get("ay", 0.0)
        accel_z = imu.get("az", 0.0)

        with self._lock:
            self._packet_count += 1
            self._last_recv_time = time.monotonic()

            # Remap sensor axes to ROV frame
            raw_yaw, raw_pitch, raw_roll = self._apply_remap(
                sensor_yaw, sensor_pitch, sensor_roll
            )
            raw_yr, raw_pr, raw_rr = self._apply_remap(
                sensor_yr, sensor_pr, sensor_rr
            )

            # Apply tare offset
            yaw = raw_yaw - self._tare_offset["yaw"]
            pitch = raw_pitch - self._tare_offset["pitch"]
            roll = raw_roll - self._tare_offset["roll"]

            self._last_data = {
                "raw": {"yaw": raw_yaw, "pitch": raw_pitch, "roll": raw_roll},
                "yaw": round(yaw, 2),
                "pitch": round(pitch, 2),
                "roll": round(roll, 2),
                "yr": round(raw_yr, 2),
                "pr": round(raw_pr, 2),
                "rr": round(raw_rr, 2),
                "ax": round(accel_x, 3),
                "ay": round(accel_y, 3),
                "az": round(accel_z, 3),
            }

        # Update data.json
        try:
            self.data_handler.update_data({
                "imu": {
                    "yaw": round(yaw, 2),
                    "pitch": round(pitch, 2),
                    "roll": round(roll, 2),
                    "yr": round(raw_yr, 2),
                    "pr": round(raw_pr, 2),
                    "rr": round(raw_rr, 2),
                    "ax": round(accel_x, 3),
                    "ay": round(accel_y, 3),
                    "az": round(accel_z, 3),
                }
            })
        except Exception as e:
            print(f"IMU: Error updating data: {e}")


def init_imu_receiver(host=UDP_IP, port=UDP_PORT, data_handler=None) -> IMUReceiver:
    """Initialize and start the IMU receiver."""
    receiver = IMUReceiver(host=host, port=port, data_handler=data_handler)
    receiver.start()
    return receiver
