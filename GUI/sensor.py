import dash
from dash import dcc, html
import dash_bootstrap_components as dbc
from components.battery import battery_component
from components.thrusters import thrusters_component
from components.sensors import sensors_component
from components.lights import lights_component
from components.depth import depth_component
from lib.utils import fetch_json_data

# old version
# def init_sensor_app() -> dash.Dash:
#     external_stylesheets = [dbc.themes.CYBORG]
#     app_sensor = dash.Dash(__name__, external_stylesheets=external_stylesheets)

#     # Layout for the sensor data app
#     app_sensor.layout = html.Div([
#         dbc.Container([
#             html.H1("ROV Sensor Monitor", className='text-center mb-4'),

#             # Section for Battery
#             dbc.Row([
#                 dbc.Col(html.H3("Battery", className='mb-3'), width=12),
#                 dbc.Col(html.Div(id='battery-display', className='mb-4'), width=12)
#             ]),

#             # Section for Thrusters
#             dbc.Row([
#                 dbc.Col(html.H3("Thrusters Power and Temp", className='mb-3'), width=12),
#                 dbc.Col(id='thruster-table', width=12)
#             ]),

#             # Section for 9DOF Sensor Data
#             dbc.Row([
#                 dbc.Col(html.H3("9DOF Sensor Data", className='mb-3'), width=12),
#                 dbc.Col(id='sensor-table', width=12)
#             ]),

#             # Section for Depth Data with Graph
#             dbc.Row([
#                 dbc.Col(html.H3("Depth Data", className='mb-3'), width=12),
#                 dbc.Col(dcc.Graph(id='depth-graph'), width=12)
#             ]),
#             dcc.Interval(id='interval-sensor', interval=1000, n_intervals=0)
#         ], fluid=True)
#     ])
#     return app_sensor

def init_sensor_app() -> dash.Dash:
    external_stylesheets = [dbc.themes.SLATE]
    app_sensor = dash.Dash(__name__, external_stylesheets=external_stylesheets)
    app_sensor.layout = dbc.Container([
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
        dcc.Interval(id='interval-sensor', interval=2000, n_intervals=0, disabled=False),
    ], fluid=True)
    return app_sensor