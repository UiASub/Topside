from flask import Flask, render_template, jsonify
from multiprocessing import Process
from lib.json_data_handler import JSONDataHandler

# Flask app for the main dashboard
app_dashboard = Flask(__name__, static_folder="static", template_folder="static/templates")
data_handler = JSONDataHandler()

@app_dashboard.route("/")
def dashboard():
    """Serve the main dashboard."""
    return render_template("layout.html")

@app_dashboard.route("/api/thrusters", methods=["GET"])
def get_thrusters():
    """API for thruster data."""
    return jsonify(data_handler.get_section("thrusters"))

@app_dashboard.route("/api/sensors", methods=["GET"])
def get_sensors():
    """API for sensor data."""
    return jsonify(data_handler.get_section("9dof"))

@app_dashboard.route("/api/lights", methods=["GET"])
def get_lights():
    """API for light data."""
    return jsonify(data_handler.get_section("lights"))

@app_dashboard.route("/api/battery", methods=["GET"])
def get_battery():
    """API for battery data."""
    return jsonify({"battery": data_handler.get_section("battery")})

@app_dashboard.route("/api/depth", methods=["GET"])
def get_depth():
    """API for depth data."""
    return jsonify(data_handler.get_section("depth"))

# Separate Flask app for video server
app_video = Flask(__name__, static_folder="static", template_folder="templates")

@app_video.route("/api/video_stream", methods=["GET"])
def video_stream():
    """API for video stream."""
    # Replace with actual video stream logic
    return jsonify({"status": "Video stream not implemented"})

# Separate Flask app for sensor server
app_sensor = Flask(__name__, static_folder="static", template_folder="templates")

@app_sensor.route("/api/sensor_update", methods=["GET"])
def sensor_update():
    """API for periodic sensor data updates."""
    # Replace with actual sensor update logic
    return jsonify({"status": "Sensor updates not implemented"})

# Function to run the dashboard server
def run_dashboard_server():
    print("Starting dashboard server on port 5000...")
    app_dashboard.run(debug=True, port=5000, use_reloader=False)

# Function to run the video server
def run_video_server():
    print("Starting video server on port 8050...")
    app_video.run(debug=False, port=8050, use_reloader=False)

# Function to run the sensor server
def run_sensor_server():
    print("Starting sensor server on port 8051...")
    app_sensor.run(debug=False, port=8051, use_reloader=False)

if __name__ == "__main__":
    # Create processes for each server
    dashboard_process = Process(target=run_dashboard_server)
    video_process = Process(target=run_video_server)
    sensor_process = Process(target=run_sensor_server)

    # Start the processes
    dashboard_process.start()
    video_process.start()
    sensor_process.start()

    # Wait for all processes to complete
    dashboard_process.join()
    video_process.join()
    sensor_process.join()
