import dash
import dash_bootstrap_components as dbc
from dash import dcc
from components.battery import battery_component
from components.thrusters import thrusters_component
from components.sensors import sensors_component
from components.lights import lights_component
from components.depth import depth_component
from components.video import video_component
import callbacks  # Import the callbacks to register them

# Initialize the Dash app with a dark theme (Cyborg)
external_stylesheets = [dbc.themes.CYBORG]
app = dash.Dash(__name__, external_stylesheets=external_stylesheets)

# Layout for the app
app.layout = dbc.Container([
    battery_component(),
    thrusters_component(),
    sensors_component(),
    lights_component(),
    depth_component(),
    video_component(),

    # Intervals for periodic updates
    dcc.Interval(id='json-interval', interval=2000, n_intervals=0),  # JSON updates every 2 seconds
    dcc.Interval(id='video-interval', interval=1000, n_intervals=0),  # Video updates every second
], fluid=True)

if __name__ == '__main__':
    app.run_server(debug=True)
