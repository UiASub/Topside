from flask import Flask, render_template, jsonify
from multiprocessing import Process
from components.video import update_video_stream
from components.sensors import fetch_sensor_data
import json

# Flask app for the main dashboard
app_dashboard = Flask(__name__, static_folder="static", template_folder="static/templates")

# Flask app for the video server
app_video = Flask(__name__)

# Flask app for the sensor server
app_sensor = Flask(__name__)

# Data file path
DATA_FILE = 'debug_server/data.json'

# Main dashboard route
@app_dashboard.route("/")
def dashboard():
    return render_template("layout.html")


# API to fetch thruster data
@app_dashboard.route("/api/thrusters", methods=["GET"])
def get_thrusters():
    try:
        with open(DATA_FILE, 'r') as json_file:
            data = json.load(json_file)
        thrusters = data.get("thrusters", {})
        return jsonify(thrusters)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# API to update video stream
@app_video.route("/api/video_stream")
def video_stream():
    return jsonify(update_video_stream())


# API to fetch sensor data
@app_sensor.route("/api/sensor_data")
def sensor_data():
    return jsonify(fetch_sensor_data())


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
