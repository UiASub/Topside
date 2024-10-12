from dash import html
import dash_bootstrap_components as dbc

def video_component():
    return dbc.Row([
        dbc.Col(html.H3("Live Video Stream", className='mb-3'), width=12),
        dbc.Col(html.Img(id='video-stream', style={'width': '640px', 'height': '480px'}), width=12)
    ])
