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
UDP_PORT = 65433  # Use a different UDP port

# Store depth data over time
depth_data = deque(maxlen=50)  # Store up to 50 data points for depth

# Initialize the Dash app with a dark theme (Cyborg)
external_stylesheets = [dbc.themes.CYBORG]
app = dash.Dash(__name__, external_stylesheets=external_stylesheets)

# Layout for the app
app.layout = html.Div([
    dbc.Container([
        html.H1("ROV Pilot Monitor", className='text-center mb-4'),

        # Connection Button
        dbc.Button("Connect to ROV", id="connect-button", color="primary", className="mb-3", n_clicks=0),

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

        # Section for Lights
        dbc.Row([
            dbc.Col(html.H3("Lights", className='mb-3'), width=12),
            dbc.Col(id='lights-display', width=12)
        ]),

        # Section for Depth Data with Graph
        dbc.Row([
            dbc.Col(html.H3("Depth Data", className='mb-3'), width=12),
            dbc.Col(dcc.Graph(id='depth-graph'), width=12),
        ]),

        # Section for Video Stream
        dbc.Row([
            dbc.Col(html.H3("Live Video Stream", className='mb-3'), width=12),
            dbc.Col(html.Img(id='video-stream', style={'width': '640px', 'height': '480px'}), width=12)
        ]),

        # Interval for updating both JSON and Video
        dcc.Interval(id='interval-component', interval=1000, n_intervals=0)  # 1-second intervals
    ], fluid=True)
])

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

# Function to fetch the video stream
def fetch_video_stream():
    try:
        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        udp_socket.settimeout(None)
        udp_socket.bind(('0.0.0.0', UDP_PORT))

        data, _ = udp_socket.recvfrom(8192)  # Matching the packet size
        print(f"Received video stream of size {len(data)} bytes")
        np_data = np.frombuffer(data, dtype=np.uint8)
        frame = cv2.imdecode(np_data, cv2.IMREAD_COLOR)

        _, buffer = cv2.imencode('.jpg', frame)
        video_base64 = base64.b64encode(buffer).decode('utf-8')

        return video_base64

    except Exception as e:
        print(f"Error receiving video stream: {e}")
        return None


# Helper function to format thruster data
def format_thruster_data(thrusters):
    rows = []
    for thruster, stats in thrusters.items():
        rows.append(html.Tr([html.Td(thruster), html.Td(f"Power: {stats['power']}W"), html.Td(f"Temp: {stats['temp']}°C")]))
    return dbc.Table(children=[html.Tbody(rows)], bordered=True, hover=True, responsive=True)

# Helper function to format 9DOF sensor data
def format_sensor_data(dof_data):
    rows = [
        html.Tr([html.Td("Acceleration"), html.Td(f"x: {dof_data['acceleration']['x']} m/s²"), html.Td(f"y: {dof_data['acceleration']['y']} m/s²"), html.Td(f"z: {dof_data['acceleration']['z']} m/s²")]),
        html.Tr([html.Td("Gyroscope"), html.Td(f"x: {dof_data['gyroscope']['x']} °/s"), html.Td(f"y: {dof_data['gyroscope']['y']} °/s"), html.Td(f"z: {dof_data['gyroscope']['z']} °/s")]),
        html.Tr([html.Td("Magnetometer"), html.Td(f"x: {dof_data['magnetometer']['x']} µT"), html.Td(f"y: {dof_data['magnetometer']['y']} µT"), html.Td(f"z: {dof_data['magnetometer']['z']} µT")])
    ]
    return dbc.Table(children=[html.Tbody(rows)], bordered=True, hover=True, responsive=True)

# Callback to handle button clicks and toggle connection state
@app.callback(
    Output('connect-button', 'children'),
    [Input('connect-button', 'n_clicks')]
)
def toggle_connection(n_clicks):
    if n_clicks % 2 == 0:
        return "Connect to ROV"
    else:
        return "Disconnect from ROV"

# Callback to update the JSON data, depth graph, and video stream
@app.callback(
    [Output('battery-display', 'children'),
     Output('thruster-table', 'children'),
     Output('sensor-table', 'children'),
     Output('lights-display', 'children'),
     Output('depth-graph', 'figure'),
     Output('video-stream', 'src')],
    [Input('interval-component', 'n_intervals')]
)
def update_dashboard(n):
    # Fetch JSON data
    data = fetch_json_data()

    # Update battery
    battery_display = f"Battery: {data.get('battery', 0)} %"

    # Update thruster data
    formatted_thrusters = format_thruster_data(data.get('thrusters', {}))

    # Update 9DOF data
    formatted_sensors = format_sensor_data(data.get('9dof', {}))

    # Update lights
    lights = data.get('lights', {})
    lights_display = html.Ul([html.Li(f"Light {i}: {lights.get(f'Light{i}', 0)} %") for i in range(1, 5)])

    # Update depth graph
    depth = data.get('depth', {}).get('dpt', 0)
    depth_data.append(depth)
    depth_graph = {
        'data': [go.Scatter(x=list(range(len(depth_data))), y=list(depth_data), mode='lines', name='Depth (m)')],
        'layout': go.Layout(title='Depth Over Time', xaxis={'title': 'Time (s)'}, yaxis={'title': 'Depth (m)'}, template='plotly_dark')
    }

    # Fetch video stream
    video_base64 = fetch_video_stream()
    if video_base64:
        video_src = f'data:image/jpeg;base64,{video_base64}'
    else:
        video_src = ""

    return battery_display, formatted_thrusters, formatted_sensors, lights_display, depth_graph, video_src

if __name__ == '__main__':
    app.run_server(debug=True)