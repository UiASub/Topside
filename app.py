from flask import Flask, render_template, jsonify
from multiprocessing import Process
from components.video import update_video_stream
from components.sensors import fetch_sensor_data

# Flask app setup
app = Flask(__name__, static_folder='js')

# Serve the HTML Dashboard
@app.route("/")
def dashboard():
    return render_template("static/templates/layout.html")

# API to update video stream
@app.route("/api/video_stream")
def video_stream():
    # Replace with your actual video stream logic
    return jsonify(update_video_stream())

# API to fetch sensor data
@app.route("/api/sensor_data")
def sensor_data():
    # Replace with your actual sensor fetching logic
    return jsonify(fetch_sensor_data())

# Function to run the video server process
def run_video_server():
    print("Starting video server on port 8050...")
    app.run(debug=False, port=8050, use_reloader=False)

# Function to run the sensor server process
def run_sensor_server():
    print("Starting sensor server on port 8051...")
    app.run(debug=True, port=8051, use_reloader=False)

if __name__ == "__main__":
    # Create processes for video and sensor servers
    video_process = Process(target=run_video_server)
    sensor_process = Process(target=run_sensor_server)

    # Start the processes
    video_process.start()
    sensor_process.start()

    # Wait for both processes to complete
    video_process.join()
    sensor_process.join()
