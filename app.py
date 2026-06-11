import atexit
import os

from flask import Flask

from lib.aruco_logger import ArucoPipelineLogger
from lib.axis_config_sender import send_axis_config
from lib.bitmask import init_bitmask
from lib.camera import init_camera, init_ip_camera, init_rpi_camera
from lib.control_telemetry import init_control_telemetry
from lib.controller import Controller
from lib.json_data_handler import JSONDataHandler
from lib.log_udp_receiver import init_log_stream
from lib.net_transport import DEFAULT_ROV_HOST
from lib.ninedof_receiver import init_imu_receiver
from lib.resource_receiver import init_resource_receiver
from lib.runtime_paths import data_dir, data_path, ensure_data_dir
from lib.setpoint_override import init_setpoint_override
from lib.system_control_client import SystemControlClient
from routes import register_routes

app = Flask(__name__, static_folder="static", template_folder="static/templates")
ensure_data_dir()

# Start background UDP sender (20 Hz)
app.config["BITMASK"] = init_bitmask(rate_hz=20.0, host=DEFAULT_ROV_HOST, port=12345)

# Initialize and start controller handler (60 Hz)
app.config["CONTROLLER"] = Controller(bitmask_client=app.config["BITMASK"], rate_hz=60.0)
app.config["CONTROLLER"].start()

# Start background IMU receiver (UDP port 5002)
app.config["IMU"] = init_imu_receiver(port=5002)

# Tracks ordered ARUCO markers for the pipeline challenge.
app.config["ARUCO_LOGGER"] = ArucoPipelineLogger()

# Load saved IMU axis mapping from config
_config = JSONDataHandler(file_path=data_path("config.json"))
_saved_axes = _config.get_section("imu_axes")
if _saved_axes:
    app.config["IMU"].set_axis_mapping(_saved_axes)

# Load saved accel axis mapping from config
_saved_accel_axes = _config.get_section("accel_axes")
if _saved_accel_axes:
    app.config["IMU"].set_accel_mapping(_saved_accel_axes)

# Send full axis config (YPR remap, accel remap, offset) to microcontroller on startup
_saved_offset = _config.get_section("imu_offset")
send_axis_config(
    imu_axes=_saved_axes,
    accel_axes=_saved_accel_axes,
    offset=_saved_offset,
    host=DEFAULT_ROV_HOST,
)

# Initialize RPi camera stream receiver.
# The receiver listens locally (0.0.0.0) and accepts RTP/H264 from the RPi sender.
rpi_cam_port = int(os.getenv("RPI_CAMERA_PORT", "6969"))
rpi_cam_bind = os.getenv("RPI_CAMERA_BIND", "0.0.0.0")
rpi_cam_latency_ms = int(os.getenv("RPI_CAMERA_LATENCY_MS", "12"))
rpi_cam_out_width = int(os.getenv("RPI_CAMERA_OUT_WIDTH", "960"))
rpi_cam_out_height = int(os.getenv("RPI_CAMERA_OUT_HEIGHT", "540"))
rpi_cam_jpeg_quality = int(os.getenv("RPI_CAMERA_JPEG_QUALITY", "70"))
rpi_cam_flip_180 = os.getenv("RPI_CAMERA_FLIP_180", "false").strip().lower() in {"1", "true", "yes", "on"}
app.config["RPI_CAMERA"] = init_rpi_camera(
    host=rpi_cam_bind,
    port=rpi_cam_port,
    latency_ms=rpi_cam_latency_ms,
    out_width=rpi_cam_out_width,
    out_height=rpi_cam_out_height,
    jpeg_quality=rpi_cam_jpeg_quality,
    flip_180=rpi_cam_flip_180,
    marker_logger=app.config["ARUCO_LOGGER"],
)

# Initialize IP camera (SMTSEC SIP-K327GS) via RTSP
_ip_camera_config = _config.get_section("ip_camera") or {}
ip_cam_active_ip = _ip_camera_config.get("active_ip") or "10.77.0.4"
ip_cam_url = os.getenv("IP_CAMERA_URL")
if ip_cam_url:
    ip_cam_active_ip = None
else:
    ip_cam_url = f"rtsp://{ip_cam_active_ip}:554/stream1"
ip_cam_out_width = int(os.getenv("IP_CAMERA_OUT_WIDTH", "960"))
ip_cam_out_height = int(os.getenv("IP_CAMERA_OUT_HEIGHT", "540"))
ip_cam_jpeg_quality = int(os.getenv("IP_CAMERA_JPEG_QUALITY", "70"))
ip_cam_flip_180 = os.getenv("IP_CAMERA_FLIP_180", "false").strip().lower() in {"1", "true", "yes", "on"}
app.config["IP_CAMERA_ACTIVE_IP"] = ip_cam_active_ip
app.config["IP_CAMERA_ACTIVE_URL"] = ip_cam_url
app.config["IP_CAMERA_SETTINGS"] = {
    "out_width": ip_cam_out_width,
    "out_height": ip_cam_out_height,
    "jpeg_quality": ip_cam_jpeg_quality,
    "flip_180": ip_cam_flip_180,
}
app.config["IP_CAMERA"] = init_ip_camera(
    url=ip_cam_url,
    out_width=ip_cam_out_width,
    out_height=ip_cam_out_height,
    jpeg_quality=ip_cam_jpeg_quality,
    flip_180=ip_cam_flip_180,
    marker_logger=app.config["ARUCO_LOGGER"],
)

# Initialize default local camera for the legacy Camera 1 feed.
# Opening and reconnecting happen in the receiver thread so app startup can continue.
default_cam_device = int(os.getenv("DEFAULT_CAMERA_DEVICE", "0"))
default_cam_jpeg_quality = int(os.getenv("DEFAULT_CAMERA_JPEG_QUALITY", "70"))
app.config["DEFAULT_CAMERA"] = init_camera(
    device_index=default_cam_device,
    jpeg_quality=default_cam_jpeg_quality,
    marker_logger=app.config["ARUCO_LOGGER"],
)

# Start background resource monitor receiver (UDP port 12346)
app.config["RESOURCE"] = init_resource_receiver(port=12346)
app.config["BITMASK"].set_resource_monitor(app.config["RESOURCE"])

# Initialize setpoint override client (UDP port 5007)
app.config["SETPOINT_OVERRIDE"] = init_setpoint_override(resource_monitor=app.config["RESOURCE"])

# Start control loop telemetry receiver (UDP port 5005)
app.config["CONTROL_TELEM"] = init_control_telemetry(port=5005)

# Start Zephyr log stream receiver (UDP port 5006)
app.config["LOG_STREAM"] = init_log_stream(port=5006)

# Initialize system control client (UDP port 5008)
app.config["SYSTEM_CONTROL"] = SystemControlClient()

register_routes(app)


def _shutdown():
    ctrl = app.config.get("CONTROLLER")
    if ctrl:
        ctrl.stop()
    bm = app.config.get("BITMASK")
    if bm:
        bm.stop()
    imu = app.config.get("IMU")
    if imu:
        imu.stop()
    rpi_cam = app.config.get("RPI_CAMERA")
    if rpi_cam:
        rpi_cam.stop()
    ip_cam = app.config.get("IP_CAMERA")
    if ip_cam:
        ip_cam.stop()
    default_cam = app.config.get("DEFAULT_CAMERA")
    if default_cam:
        default_cam.stop()
    resource = app.config.get("RESOURCE")
    if resource:
        resource.stop()
    ctrl_telem = app.config.get("CONTROL_TELEM")
    if ctrl_telem:
        ctrl_telem.stop()
    log_stream = app.config.get("LOG_STREAM")
    if log_stream:
        log_stream.stop()
    sp_override = app.config.get("SETPOINT_OVERRIDE")
    if sp_override:
        sp_override.close()
    system_control = app.config.get("SYSTEM_CONTROL")
    if system_control:
        system_control.close()


atexit.register(_shutdown)


def run_dashboard_server():
    print(f"Using data directory: {data_dir()}")
    print("Starting dashboard server on port 5000...")
    app.run(debug=True, port=5000, use_reloader=False, threaded=True)


if __name__ == "__main__":
    run_dashboard_server()
