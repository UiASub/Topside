from flask import Flask
from lib.camera import init_camera
from routes import register_routes
from lib.bitmask import init_bitmask
import atexit

app = Flask(__name__, static_folder="static", template_folder="static/templates")

# Start background UDP sender (20 Hz)
app.config["BITMASK"] = init_bitmask(rate_hz=20.0, host="192.168.1.100", port=12345)

register_routes(app)
camera = init_camera()

def _shutdown():
    bm = app.config.get("BITMASK")
    if bm: bm.stop()
atexit.register(_shutdown)

def run_dashboard_server():
    print("Starting dashboard server on port 5000...")
    app.run(debug=True, port=5000, use_reloader=False)

if __name__ == "__main__":
    run_dashboard_server()
