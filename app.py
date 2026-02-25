from flask import Flask
from lib.camera import init_camera, init_rpi_camera
from lib.controller import Controller
from routes import register_routes
from lib.bitmask import init_bitmask
from lib.ninedof_receiver import init_ninedof_receiver
from lib.resource_receiver import init_resource_receiver
import atexit
import os

app = Flask(__name__, static_folder="static", template_folder="static/templates")

# Start background UDP sender (20 Hz)
app.config["BITMASK"] = init_bitmask(rate_hz=20.0, host="192.168.1.100", port=12345)

# Initialize and start controller handler (60 Hz)
app.config["CONTROLLER"] = Controller(bitmask_client=app.config["BITMASK"], rate_hz=60.0)
app.config["CONTROLLER"].start()

# Start background 9DOF sensor receiver (UDP port 5002)
app.config["NINEDOF"] = init_ninedof_receiver(port=5002)

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
# Start background resource monitor receiver (UDP port 12346)
app.config["RESOURCE"] = init_resource_receiver(port=12346)

register_routes(app)
camera = init_camera()

def _shutdown():
    ctrl = app.config.get("CONTROLLER")
    if ctrl: ctrl.stop()
    bm = app.config.get("BITMASK")
    if bm: bm.stop()
    ninedof = app.config.get("NINEDOF")
    if ninedof: ninedof.stop()
    rpi_cam = app.config.get("RPI_CAMERA")
    if rpi_cam: rpi_cam.stop()
    resource = app.config.get("RESOURCE")
    if resource: resource.stop()
atexit.register(_shutdown)

def run_dashboard_server():
    print("Starting dashboard server on port 5000...")
    app.run(debug=True, port=5000, use_reloader=False, threaded=True)

if __name__ == "__main__":
    run_dashboard_server()
