from flask import Flask
from lib.camera import init_camera
from lib.controller import Controller
from routes import register_routes
from lib.bitmask import init_bitmask
from lib.ninedof_receiver import init_ninedof_receiver
from lib.resource_receiver import init_resource_receiver
import atexit

app = Flask(__name__, static_folder="static", template_folder="static/templates")

# Start background UDP sender (20 Hz)
app.config["BITMASK"] = init_bitmask(rate_hz=20.0, host="192.168.1.100", port=12345)

# Initialize and start controller handler (60 Hz)
app.config["CONTROLLER"] = Controller(bitmask_client=app.config["BITMASK"], rate_hz=60.0)
app.config["CONTROLLER"].start()

# Start background 9DOF sensor receiver (UDP port 5002)
app.config["NINEDOF"] = init_ninedof_receiver(port=5002)

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
    resource = app.config.get("RESOURCE")
    if resource: resource.stop()
atexit.register(_shutdown)

def run_dashboard_server():
    print("Starting dashboard server on port 5000...")
    app.run(debug=True, port=5000, use_reloader=False)

if __name__ == "__main__":
    run_dashboard_server()
