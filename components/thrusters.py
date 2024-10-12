from dash import html
import dash_bootstrap_components as dbc

def thrusters_component():
    return dbc.Row([
        dbc.Col(html.H3("Thrusters Power and Temp", className='mb-3'), width=12),
        dbc.Col(html.Div(id='thruster-table'), width=12)
    ])
