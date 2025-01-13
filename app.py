from flask import Flask, render_template, jsonify, Response
from multiprocessing import Process
from lib.json_data_handler import JSONDataHandler
from lib.camera import init_camera, generate_frames

# Flask app for the main dashboard
app_dashboard = Flask(
    __name__,
    static_folder="static",
    template_folder="static/templates"
)
data_handler = JSONDataHandler()

# Initialize camera
camera = init_camera()

@app_dashboard.route("/")
def dashboard():
    """Serve the main dashboard."""
    return render_template("layout.html")

@app_dashboard.route("/Camera1")
def camera1():
    """Render the camera1.html template."""
    return render_template("camera1.html")

@app_dashboard.route("/video_feed")
def video_feed():
    """Return a streaming MJPEG response from the camera."""
    return Response(
        generate_frames(camera),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )

@app_dashboard.route("/api/thrusters", methods=["GET"])
def get_thrusters():
    return jsonify(data_handler.get_section("thrusters"))

@app_dashboard.route("/api/sensors", methods=["GET"])
def get_sensors():
    return jsonify(data_handler.get_section("9dof"))

@app_dashboard.route("/api/lights", methods=["GET"])
def get_lights():
    return jsonify(data_handler.get_section("lights"))

@app_dashboard.route("/api/battery", methods=["GET"])
def get_battery():
    return jsonify({"battery": data_handler.get_section("battery")})

@app_dashboard.route("/api/depth", methods=["GET"])
def get_depth():
    return jsonify(data_handler.get_section("depth"))

# Optional: separate Flask apps, if needed
app_video = Flask(__name__, static_folder="static", template_folder="templates")
app_sensor = Flask(__name__, static_folder="static", template_folder="templates")

@app_video.route("/api/video_stream", methods=["GET"])
def video_stream():
    return jsonify({"status": "Video stream not implemented"})

@app_sensor.route("/api/sensor_update", methods=["GET"])
def sensor_update():
    return jsonify({"status": "Sensor updates not implemented"})

# Function to run the dashboard server
def run_dashboard_server():
    print("Starting dashboard server on port 5000...")
    app_dashboard.run(debug=True, port=5000, use_reloader=False)

if __name__ == "__main__":
    # Create processes for each server
    dashboard_process = Process(target=run_dashboard_server)

    # Start the processes
    dashboard_process.start()

    # Wait for all processes to complete
    dashboard_process.join()
