from dash import html
import dash_bootstrap_components as dbc

def battery_component():
    return dbc.Row([
        dbc.Col(html.H3("Battery", className='mb-3'), width=12),
        dbc.Col(html.Div(id='battery-display', className='mb-4'), width=12)
    ])
