from dash import html
import dash_bootstrap_components as dbc

def lights_component():
    return dbc.Row([
        dbc.Col(html.H3("Lights", className='mb-3'), width=12),
        dbc.Col(html.Div(id='lights-display'), width=12)
    ])
