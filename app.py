import threading
import dash
from dash import dcc, html
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output
from collections import deque
from lib.sensor_handling import *
from lib.video_stream import *
from lib.utils import *
from GUI.sensor import *
from GUI.video import *
from multiprocessing import Process


# Backend server details
HOST = '127.0.0.1'
TCP_PORT = 65432  # Port for JSON data
UDP_PORT = 65433  # Port for video stream
UDP_BUFFER_SIZE = 2**16

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

if __name__ == '__main__':
    # Start both apps in separate threads
    video_process = Process(target=run_video_app)
    sensor_process = Process(target=run_sensor_app)

    video_process.start()
    sensor_process.start()

    video_process.join()
    sensor_process.join()