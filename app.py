from flask import Flask
from lib.camera import init_camera, init_rpi_camera, init_ip_camera
from lib.controller import Controller
from routes import register_routes
from lib.bitmask import init_bitmask
from lib.ninedof_receiver import init_imu_receiver
from lib.axis_config_sender import send_axis_config
from lib.resource_receiver import init_resource_receiver
from lib.json_data_handler import JSONDataHandler
import atexit
import os

app = Flask(__name__, static_folder="static", template_folder="static/templates")

# Start background UDP sender (20 Hz)
app.config["BITMASK"] = init_bitmask(rate_hz=20.0, host="192.168.1.100", port=12345)

# Initialize and start controller handler (60 Hz)
app.config["CONTROLLER"] = Controller(bitmask_client=app.config["BITMASK"], rate_hz=60.0)
app.config["CONTROLLER"].start()

# Start background IMU receiver (UDP port 5002)
app.config["IMU"] = init_imu_receiver(port=5002)

# Load saved IMU axis mapping from config
_config = JSONDataHandler(file_path="data/config.json")
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
)

# Initialize IP camera (SMTSEC SIP-K327GS) via RTSP
ip_cam_url = os.getenv("IP_CAMERA_URL", "rtsp://192.168.1.168:554/stream1")
ip_cam_out_width = int(os.getenv("IP_CAMERA_OUT_WIDTH", "960"))
ip_cam_out_height = int(os.getenv("IP_CAMERA_OUT_HEIGHT", "540"))
ip_cam_jpeg_quality = int(os.getenv("IP_CAMERA_JPEG_QUALITY", "70"))
ip_cam_flip_180 = os.getenv("IP_CAMERA_FLIP_180", "false").strip().lower() in {"1", "true", "yes", "on"}
app.config["IP_CAMERA"] = init_ip_camera(
    url=ip_cam_url,
    out_width=ip_cam_out_width,
    out_height=ip_cam_out_height,
    jpeg_quality=ip_cam_jpeg_quality,
    flip_180=ip_cam_flip_180,
)
# Start background resource monitor receiver (UDP port 12346)
app.config["RESOURCE"] = init_resource_receiver(port=12346)

register_routes(app)
camera = init_camera()

def _shutdown():
    ctrl = app.config.get("CONTROLLER")
    if ctrl: ctrl.stop()
    bm = app.config.get("BITMASK")
    if bm: bm.stop()
    imu = app.config.get("IMU")
    if imu: imu.stop()
    rpi_cam = app.config.get("RPI_CAMERA")
    if rpi_cam: rpi_cam.stop()
    ip_cam = app.config.get("IP_CAMERA")
    if ip_cam: ip_cam.stop()
    resource = app.config.get("RESOURCE")
    if resource: resource.stop()
atexit.register(_shutdown)

def run_dashboard_server():
    print("Starting dashboard server on port 5000...")
    app.run(debug=True, port=5000, use_reloader=False, threaded=True)

if __name__ == "__main__":
    run_dashboard_server()
