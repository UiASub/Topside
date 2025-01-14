from flask import Flask, render_template, jsonify, Response
from multiprocessing import Process
from lib.json_data_handler import JSONDataHandler
from lib.camera import init_camera, generate_frames
from routes import register_routes

# Flask app for the main dashboard
app = Flask(
    __name__,
    static_folder="static",
    template_folder="static/templates"
)
data_handler = JSONDataHandler()

register_routes(app)

# Initialize camera
camera = init_camera()

# Function to run the dashboard server
def run_dashboard_server():
    print("Starting dashboard server on port 5000...")
    app.run(debug=True, port=5000, use_reloader=False)

if __name__ == "__main__":
    # Create processes for each server
    dashboard_process = Process(target=run_dashboard_server)

    # Start the processes
    dashboard_process.start()

    # Wait for all processes to complete
    dashboard_process.join()
