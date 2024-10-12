from dash import html
import dash_bootstrap_components as dbc

def sensors_component():
    return dbc.Row([
        dbc.Col(html.H3("9DOF Sensor Data", className='mb-3'), width=12),
        dbc.Col(html.Div(id='sensor-table'), width=12)
    ])
