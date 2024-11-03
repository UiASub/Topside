import dash
from dash import dcc, html, Input, Output
import dash_bootstrap_components as dbc
from lib.utils import fetch_json_data  # Import the data fetching function from the appropriate module
import plotly.graph_objs as go
import pandas as pd

def init_video_app() -> dash.Dash:
    external_stylesheets = [dbc.themes.CYBORG]  # Using a dark theme that fits an underwater control panel
    app_video = dash.Dash(__name__, external_stylesheets=external_stylesheets)

    # Layout for the video stream app with an underwater ROV theme
    app_video.layout = html.Div([
        dbc.Container([
            html.H1("ROV Control Center", className='text-center mb-3', style={
                "color": "#00bfff",  # Aqua color for a more thematic effect
                "font-family": "SF Pro, Arial, sans-serif",
                "text-shadow": "2px 2px 4px #000",  # Subtle shadow for a glowing effect
                "font-size": "2.5rem"
            }),
            dbc.Row([
                dbc.Col(html.Div([
                    html.H4("Telemetry Data", className='text-center mb-3', style={
                        "color": "#87ceeb",  # Light blue color
                        "font-family": "SF Pro, Arial, sans-serif",
                        "text-shadow": "1px 1px 3px #000",
                        "font-size": "1.5rem"
                    }),
                    html.Div([
                        html.I(className="bi bi-battery-half", style={"margin-right": "8px"}),
                        "Battery: ", html.Span("N/A", id='battery-level', style={"font-size": "1.2rem", "color": "#00ff7f"})
                    ], className='mb-2'),
                    html.Div([
                        html.I(className="bi bi-compass", style={"margin-right": "8px"}),
                        "Heading: ", html.Span("N/A", id='heading', style={"font-size": "1.2rem", "color": "#ffdd57"})
                    ], className='mb-2'),
                    html.Div([
                        html.I(className="bi bi-arrow-up-down", style={"margin-right": "8px"}),
                        "Pitch: ", html.Span("N/A", id='pitch', style={"font-size": "1.2rem", "color": "#ff6347"})
                    ], className='mb-2'),
                    html.Div([
                        html.I(className="bi bi-arrow-repeat", style={"margin-right": "8px"}),
                        "Roll: ", html.Span("N/A", id='roll', style={"font-size": "1.2rem", "color": "#ff6347"})
                    ], className='mb-2'),
                    html.Div([
                        html.I(className="bi bi-speedometer2", style={"margin-right": "8px"}),
                        "Depth: ", html.Span("N/A", id='depth', style={"font-size": "1.2rem", "color": "#00bfff"})
                    ], className='mb-2'),
                    dcc.Graph(id='depth-graph', style={"height": "300px"})
                ]), width=3, style={
                    "background-color": "#1c1c1c",  # Dark panel background for contrast
                    "border-radius": "10px",
                    "padding": "10px",
                    "box-shadow": "0px 0px 15px rgba(0, 0, 0, 0.7)"
                }),
                dbc.Col([
                    html.H3("Live Video Feed", className='text-center mb-3', style={
                        "color": "#00bfff",  # Aqua color
                        "font-family": "SF Pro, Arial, sans-serif",
                        "text-shadow": "2px 2px 4px #000",
                        "font-size": "2rem"
                    }),
                    html.Div([
                        html.Img(id='video-stream', style={
                            'width': '95%',
                            'height': 'auto',
                            'border': '2px solid #00bfff',  # Aqua border to match the theme
                            'box-shadow': '0px 0px 20px rgba(0, 191, 255, 0.7)',  # Glowing shadow effect
                            'border-radius': '10px',
                            'margin': '0 auto',
                            'display': 'block'
                        })
                    ])
                ], width=9)
            ], align='center'),
            dcc.Interval(id='interval-video', interval=1000, n_intervals=0)  # Update every second
        ], fluid=True, style={"max-width": "1200px", "margin": "0 auto"})
    ])

    depth_data = []

    @app_video.callback(
        [
            Output('battery-level', 'children'),
            Output('heading', 'children'),
            Output('pitch', 'children'),
            Output('roll', 'children'),
            Output('depth', 'children'),
            Output('depth-graph', 'figure')
        ],
        [Input('interval-video', 'n_intervals')]
    )
    def update_video_info(n):
        data = fetch_json_data()  # Use the data-fetching function from sensor_handling.py
        battery = f"{data.get('battery', 'N/A')}%"
        heading = f"{data.get('9dof', {}).get('gyroscope', {}).get('x', 'N/A')}°"
        pitch = f"{data.get('9dof', {}).get('gyroscope', {}).get('y', 'N/A')}°"
        roll = f"{data.get('9dof', {}).get('gyroscope', {}).get('z', 'N/A')}°"
        depth = f"{data.get('depth', {}).get('dpt', 'N/A')}m / {data.get('depth', {}).get('dptSet', 'N/A')}m"

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