import dash
from dash import dcc, html, Input, Output, State
import dash_bootstrap_components as dbc
from lib.utils import fetch_json_data
import plotly.graph_objs as go
import pandas as pd


def init_video_app() -> dash.Dash:
    external_stylesheets = [dbc.themes.CYBORG]
    app_video = dash.Dash(__name__, external_stylesheets=external_stylesheets)

    # Layout for the full-screen video stream app with a toggleable telemetry overlay
    app_video.layout = html.Div([
        html.Div([
            html.Button("Toggle Telemetry", id="toggle-overlay", className="btn btn-primary", style={
                "position": "absolute", "top": "10px", "right": "10px", "z-index": "2"
            }),
            html.Div(id="telemetry-overlay", style={
                "display": "none",  # Hidden by default
                "position": "absolute", "top": "20px", "right": "20px", "width": "300px",
                "background-color": "#1c1c1c", "padding": "15px", "border-radius": "10px",
                "box-shadow": "0px 0px 15px rgba(0, 0, 0, 0.7)", "z-index": "3"
            }, children=[
                html.H4("Telemetry Data",
                        style={"color": "#87ceeb", "font-family": "Arial", "text-shadow": "1px 1px 3px #000"}),
                html.Div(["Battery: ", html.Span("N/A", id='battery-level')]),
                html.Div(["Heading: ", html.Span("N/A", id='heading'), html.Button("Lock", id="lock-heading")]),
                html.Div(["Pitch: ", html.Span("N/A", id='pitch'), html.Button("Lock", id="lock-pitch")]),
                html.Div(["Roll: ", html.Span("N/A", id='roll'), html.Button("Lock", id="lock-roll")]),
                html.Div(["Depth: ", html.Span("N/A", id='depth'), html.Button("Lock", id="lock-depth")]),
                dcc.Graph(id='depth-graph', style={"height": "200px", "margin-top": "10px"})
            ]),
            html.Div([
                html.Img(id='video-stream', style={
                    'width': '100vw', 'height': '100vh', 'object-fit': 'cover'
                })
            ])
        ], style={"position": "relative", "overflow": "hidden", "width": "100vw", "height": "100vh"}),
        # Full-screen video wrapper
        dcc.Interval(id='interval-video', interval=1000, n_intervals=0)
    ])

    depth_data = []
    locks = {
        "battery": None,
        "heading": None,
        "pitch": None,
        "roll": None,
        "depth": None
    }

    # Toggle telemetry overlay visibility
    @app_video.callback(
        Output("telemetry-overlay", "style"),
        Input("toggle-overlay", "n_clicks"),
        State("telemetry-overlay", "style"),
    )
    def toggle_overlay(n_clicks, current_style):
        if n_clicks and current_style["display"] == "none":
            current_style["display"] = "block"
        elif n_clicks:
            current_style["display"] = "none"
        return current_style

    # Update telemetry data and handle locking of values
    @app_video.callback(
        [
            Output('battery-level', 'children'),
            Output('heading', 'children'),
            Output('pitch', 'children'),
            Output('roll', 'children'),
            Output('depth', 'children'),
            Output('depth-graph', 'figure')
        ],
        [Input('interval-video', 'n_intervals')],
        [
         Input('lock-heading', 'n_clicks'),
         Input('lock-pitch', 'n_clicks'),
         Input('lock-roll', 'n_clicks'),
         Input('lock-depth', 'n_clicks')]
    )
    def update_video_info(n, lock_heading, lock_pitch, lock_roll, lock_depth):
        data = fetch_json_data()

        # Get and lock telemetry data
        battery = f"{data.get('battery', 'N/A')}%"
        heading = f"{data.get('9dof', {}).get('gyroscope', {}).get('x', 'N/A')}°"
        pitch = f"{data.get('9dof', {}).get('gyroscope', {}).get('y', 'N/A')}°"
        roll = f"{data.get('9dof', {}).get('gyroscope', {}).get('z', 'N/A')}°"
        depth = f"{data.get('depth', {}).get('dpt', 'N/A')}m / {data.get('depth', {}).get('dptSet', 'N/A')}m"

        # Handle "lock" functionality
        for key, lock_click in zip(["heading", "pitch", "roll", "depth"],
                                   [lock_heading, lock_pitch, lock_roll, lock_depth]):
            if lock_click:
                locks[key] = locals()[key]  # Save locked value
            locals()[key] = locks[key] if locks[key] is not None else locals()[key]

        # Update depth data for graph
        current_depth = data.get('depth', {}).get('dpt', None)
        if current_depth is not None:
            depth_data.append(current_depth)

        # Create depth graph
        depth_fig = go.Figure()
        depth_fig.add_trace(go.Scatter(y=depth_data, mode='lines', line=dict(color='#00bfff')))
        depth_fig.update_layout(
            margin=dict(l=0, r=0, t=0, b=0),
            paper_bgcolor="#1c1c1c",
            plot_bgcolor="#1c1c1c",
            font=dict(color="white"),
            xaxis_title="Time",
            yaxis_title="Depth (m)"
        )

        return battery, heading, pitch, roll, depth, depth_fig

    return app_video