import dash
from dash import dcc, html
import dash_bootstrap_components as dbc
from components.battery import battery_component
from components.thrusters import thrusters_component
from components.sensors import sensors_component
from components.lights import lights_component
from components.depth import depth_component
from lib.utils import fetch_json_data
from dash.dependencies import Input, Output
#from pipeline.pipeline_follow import follow_pipeline, stop_following_pipeline


def init_sensor_app() -> dash.Dash:
    external_stylesheets = [dbc.themes.SLATE]
    app_sensor = dash.Dash(__name__, external_stylesheets=external_stylesheets)
    app_sensor.layout = dbc.Container([
        html.H1("ROV Control Panel", className="text-center"),

        # Autonomous mode toggle button
        dbc.Row([
            dbc.Col(html.H3("Autonomous Mode", className='mb-3'), width=12),
            dbc.Col(dbc.Button("Toggle Autonomous Mode", id='autonomous-toggle', color='primary', n_clicks=0), width=12)
        ]),

        # Other components for displaying data
        battery_component(),
        thrusters_component(),
        sensors_component(),
        lights_component(),
        depth_component(),

        # Intervals for periodic updates
        dcc.Interval(id='interval-sensor', interval=2000, n_intervals=0, disabled=False),
    ], fluid=True)

    @app_sensor.callback(
        Output('autonomous-toggle', 'children'),
        Input('autonomous-toggle', 'n_clicks')
    )
    def toggle_autonomous_mode(n_clicks):
        if n_clicks % 2 == 1:
            follow_pipeline()
            return "Autonomous Mode: ON"
        else:
            stop_following_pipeline()
            return "Autonomous Mode: OFF"

    return app_sensor
