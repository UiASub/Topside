from dash import dcc, html
import dash_bootstrap_components as dbc

def depth_component():
    return dbc.Row([
        dbc.Col(html.H3("Depth Data", className='mb-3'), width=12),
        dbc.Col(dcc.Graph(id='depth-graph'), width=12),
    ])
