import threading
import dash
from dash import dcc, html
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output
import socket
import struct
import json
import gzip
import base64
import cv2
import numpy as np
import plotly.graph_objs as go
from collections import deque

# Backend server details
HOST = '127.0.0.1'
TCP_PORT = 65432  # Port for JSON data
UDP_PORT = 65433  # Port for video stream

# Store depth data over time
depth_data = deque(maxlen=50)

# Initialize Dash apps
external_stylesheets = [dbc.themes.CYBORG]
app_video = dash.Dash(__name__, external_stylesheets=external_stylesheets)
app_sensor = dash.Dash(__name__, external_stylesheets=external_stylesheets)

# Layout for the video stream app
app_video.layout = html.Div([
    dbc.Container([
        html.H1("ROV Video Stream", className='text-center mb-4'),
        dbc.Row([
            dbc.Col(html.H3("Live Video Stream", className='mb-3'), width=12),
            dbc.Col(html.Img(id='video-stream', style={'width': '640px', 'height': '480px'}), width=12)
        ]),
        dcc.Interval(id='interval-video', interval=1000, n_intervals=0)
    ], fluid=True)
])

# Layout for the sensor data app
app_sensor.layout = html.Div([
    dbc.Container([
        html.H1("ROV Sensor Monitor", className='text-center mb-4'),

        # Section for Battery
        dbc.Row([
            dbc.Col(html.H3("Battery", className='mb-3'), width=12),
            dbc.Col(html.Div(id='battery-display', className='mb-4'), width=12)
        ]),

        # Section for Thrusters
        dbc.Row([
            dbc.Col(html.H3("Thrusters Power and Temp", className='mb-3'), width=12),
            dbc.Col(id='thruster-table', width=12)
        ]),

        # Section for 9DOF Sensor Data
        dbc.Row([
            dbc.Col(html.H3("9DOF Sensor Data", className='mb-3'), width=12),
            dbc.Col(id='sensor-table', width=12)
        ]),

        # Section for Depth Data with Graph
        dbc.Row([
            dbc.Col(html.H3("Depth Data", className='mb-3'), width=12),
            dbc.Col(dcc.Graph(id='depth-graph'), width=12)
        ]),
        dcc.Interval(id='interval-sensor', interval=1000, n_intervals=0)
    ], fluid=True)
])

# Function to fetch the video stream
def fetch_video_stream():
    try:
        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        udp_socket.settimeout(None)
        udp_socket.bind(('0.0.0.0', UDP_PORT))

        data, _ = udp_socket.recvfrom(8192)
        np_data = np.frombuffer(data, dtype=np.uint8)
        frame = cv2.imdecode(np_data, cv2.IMREAD_COLOR)

        _, buffer = cv2.imencode('.jpg', frame)
        video_base64 = base64.b64encode(buffer).decode('utf-8')

        return video_base64

    except Exception as e:
        print(f"Error receiving video stream: {e}")
        return None

# Callback to update the video stream
@app_video.callback(
    Output('video-stream', 'src'),
    [Input('interval-video', 'n_intervals')]
)
def update_video(n):
    video_base64 = fetch_video_stream()
    if video_base64:
        return f'data:image/jpeg;base64,{video_base64}'
    return ""

# Function to fetch JSON data
def fetch_json_data():
    try:
        tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcp_socket.connect((HOST, TCP_PORT))

        # Read data length (first 4 bytes)
        data_length = tcp_socket.recv(4)
        if not data_length:
            return {}

        # Unpack the length of the compressed data
        data_length = struct.unpack('>I', data_length)[0]

        # Receive the actual data
        compressed_data = tcp_socket.recv(data_length)

        # Decompress the data
        json_data = gzip.decompress(compressed_data).decode('utf-8')

        # Parse the JSON data
        data = json.loads(json_data)

        tcp_socket.close()
        return data

    except Exception as e:
        print(f"Error receiving JSON data: {e}")
        return {}

# Callback to update sensor data
@app_sensor.callback(
    [Output('battery-display', 'children'),
     Output('thruster-table', 'children'),
     Output('sensor-table', 'children'),
     Output('depth-graph', 'figure')],
    [Input('interval-sensor', 'n_intervals')]
)
def update_sensors(n):
    data = fetch_json_data()

    # Update battery
    battery_display = f"Battery: {data.get('battery', 0)} %"

    # Update thruster data
    thruster_data = data.get('thrusters', {})
    rows = [html.Tr([html.Td(thruster), html.Td(f"Power: {stats['power']}W"), html.Td(f"Temp: {stats['temp']}°C")]) for thruster, stats in thruster_data.items()]
    formatted_thrusters = dbc.Table(children=[html.Tbody(rows)], bordered=True, hover=True, responsive=True)

    # Update 9DOF data
    dof_data = data.get('9dof', {})
    rows = [
        html.Tr([html.Td("Acceleration"), html.Td(f"x: {dof_data['acceleration']['x']} m/s²"), html.Td(f"y: {dof_data['acceleration']['y']} m/s²"), html.Td(f"z: {dof_data['acceleration']['z']} m/s²")]),
        html.Tr([html.Td("Gyroscope"), html.Td(f"x: {dof_data['gyroscope']['x']} °/s"), html.Td(f"y: {dof_data['gyroscope']['y']} °/s"), html.Td(f"z: {dof_data['gyroscope']['z']} °/s")]),
        html.Tr([html.Td("Magnetometer"), html.Td(f"x: {dof_data['magnetometer']['x']} µT"), html.Td(f"y: {dof_data['magnetometer']['y']} µT"), html.Td(f"z: {dof_data['magnetometer']['z']} µT")])
    ]
    formatted_sensors = dbc.Table(children=[html.Tbody(rows)], bordered=True, hover=True, responsive=True)

    # Update depth graph
    depth = data.get('depth', {}).get('dpt', 0)
    depth_data.append(depth)
    depth_graph = {
        'data': [go.Scatter(x=list(range(len(depth_data))), y=list(depth_data), mode='lines', name='Depth (m)')],
        'layout': go.Layout(title='Depth Over Time', xaxis={'title': 'Time (s)'}, yaxis={'title': 'Depth (m)'}, template='plotly_dark')
    }

    return battery_display, formatted_thrusters, formatted_sensors, depth_graph

# Function to run the video stream app
def run_video_app():
    app_video.run(debug=False, port=8050)

# Function to run the sensor data app
def run_sensor_app():
    app_sensor.run(debug=False, port=8051)

if __name__ == '__main__':
    # Start both apps in separate threads
    video_thread = threading.Thread(target=run_video_app)
    sensor_thread = threading.Thread(target=run_sensor_app)

    video_thread.start()
    sensor_thread.start()

    video_thread.join()
    sensor_thread.join()