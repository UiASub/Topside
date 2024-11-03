import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output
from collections import deque
from lib.sensor_handling import *
from lib.video_stream import *
from lib.utils import *
from lib.eventlogger import logger
from GUI.sensor import *
from GUI.video import *
from multiprocessing import Process
import traceback
import signal

# Initialize logger
logger.log_info("Logger initialized.")

# Store depth data over time
depth_data = deque(maxlen=50)

# Initialize Dash apps
external_stylesheets = [dbc.themes.CYBORG]

# Define the video stream app
app_video = init_video_app()
# Callback to update the video stream
app_video.callback(
    Output('video-stream', 'src'),
    [Input('interval-video', 'n_intervals')]
)(update_video)

# Function to run the video stream app
def run_video_app():
    app_video.run(debug=False, port=8050, use_reloader=False)


# Define the sensor data app
app_sensor = init_sensor_app()
# Callback to update sensor data
app_sensor.callback(
    [Output('battery-display', 'children'),
     Output('thruster-table', 'children'),
     Output('sensor-table', 'children'),
     Output('depth-graph', 'figure')],
    [Input('interval-sensor', 'n_intervals')]
)(update_sensors)

# Function to run the sensor data app
def run_sensor_app():
    app_sensor.run(debug=True, port=8051, use_reloader=False)
    

def start_process(process, process_name):
    try:
        process.start()
        logger.log_info(f"{process_name} started.")
    except Exception as e:
        logger.log_error(f"Failed to start {process_name}. Exception: {e}")
        traceback.print_exc()  # Optional: Prints full traceback for debugging purposes
        
def handle_shutdown(signum, frame):
    logger.log_info("Shutdown signal received. Terminating processes...")
    if video_process.is_alive():
        video_process.terminate()
        logger.log_info("Video app terminated.")
    if sensor_process.is_alive():
        sensor_process.terminate()
        logger.log_info("Sensor app terminated.")
    exit(0)  # Exits the main program after cleanup

if __name__ == '__main__':
    # Initialize processes
    video_process = Process(target=run_video_app)
    sensor_process = Process(target=run_sensor_app)
    
    # Register the signal handler for graceful shutdown
    signal.signal(signal.SIGINT, handle_shutdown)

    # Start processes with logging
    start_process(video_process, "Video app")
    start_process(sensor_process, "Sensor app")

    # Wait for both processes to complete
    try:
        video_process.join()
        sensor_process.join()
    except KeyboardInterrupt:
        # This part may not run as SIGINT is already handled by the signal handler
        handle_shutdown(None, None)