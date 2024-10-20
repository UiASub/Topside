import dash
from dash import dcc, html
import dash_bootstrap_components as dbc

def init_video_app() -> dash.Dash:
    external_stylesheets = [dbc.themes.CYBORG]
    app_video = dash.Dash(__name__, external_stylesheets=external_stylesheets)

    # Layout for the video stream app
    app_video.layout = html.Div([
        dbc.Container([
            html.H1("ROV Video Stream", className='text-center mb-4'),
            dbc.Row([
                dbc.Col(html.H3("Live Video Stream", className='mb-3'), width=12),
                dbc.Col(html.Img(id='video-stream', style={'width': '640px', 'height': '480px'}), width=12)
            ]),
            dcc.Interval(id='interval-video', interval=50, n_intervals=0)
        ], fluid=True)
    ])
    return app_video
