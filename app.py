import dash
import dash_bootstrap_components as dbc
from dash import dcc, html
from components.battery import battery_component
from components.thrusters import thrusters_component
from components.sensors import sensors_component
from components.lights import lights_component
from components.depth import depth_component
from video_window import open_video_stream
from utils import fetch_json_data
import time

# Initialize the Dash app with a dark theme (Cyborg)
external_stylesheets = [dbc.themes.CYBORG]
app = dash.Dash(__name__, external_stylesheets=external_stylesheets)

# Test backend connection by fetching JSON data immediately
data = fetch_json_data()
if data:
    print("Connected to backend and received JSON data.")
else:
    print("Failed to connect to backend for JSON data.")

# Open video stream without threading for now
open_video_stream()

# Layout for the app
app.layout = dbc.Container([
    html.H1("ROV Control Panel", className="text-center"),

    # Display the connection status
    html.Div(id='connection-status', children='Connecting to ROV...', style={'margin-top': '10px'}),

    # Other components for displaying data
    battery_component(),
    thrusters_component(),
    sensors_component(),
    lights_component(),
    depth_component(),

    # Intervals for periodic updates
    dcc.Interval(id='json-interval', interval=2000, n_intervals=0, disabled=False),
], fluid=True)

if __name__ == '__main__':
    app.run_server(debug=True)
