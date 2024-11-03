from collections import deque

from dash import dcc, html
import dash_bootstrap_components as dbc
import plotly.graph_objs as go
from lib.utils import fetch_json_data
from lib.eventlogger import logger

def update_sensors(n):
    # Fetch data from the JSON server
    try:
        data = fetch_json_data()
        logger.log_info("Successfully fetched data from fetch_json_data()")
    except Exception as e:
        logger.log_error(f"Error fetching data: {e}")
        return None  # Exit early if data fetch fails
    
    # Store depth data over time
    depth_data = deque(maxlen=50)

    # Update battery
    battery_display = f"Battery: {data.get('battery', 0)} %"

    # Update thruster data
    thruster_data = data.get('thrusters', {})
    rows = [
        html.Tr([
            html.Td(thruster), 
            html.Td(f"Power: {stats['power']}W"), 
            html.Td(f"Temp: {stats['temp']}°C")
            ]) for thruster, stats in thruster_data.items()]
    formatted_thrusters = dbc.Table(children=[html.Tbody(rows)], bordered=True, hover=True, responsive=True)

    # Update 9DOF data
    dof_data = data.get('9dof', {})
    rows = [
        html.Tr([html.Td("Acceleration"), html.Td(f"x: {dof_data['acceleration']['x']} m/s²"), html.Td(f"y: {dof_data['acceleration']['y']} m/s²"), html.Td(f"z: {dof_data['acceleration']['z']} m/s²")]),
        html.Tr([html.Td("Gyroscope"), html.Td(f"x: {dof_data['gyroscope']['x']} °/s"), html.Td(f"y: {dof_data['gyroscope']['y']} °/s"), html.Td(f"z: {dof_data['gyroscope']['z']} °/s")]),
        html.Tr([html.Td("Magnetometer"), html.Td(f"x: {dof_data['magnetometer']['x']} µT"), html.Td(f"y: {dof_data['magnetometer']['y']} µT"), html.Td(f"z: {dof_data['magnetometer']['z']} µT")])
    ]
    formatted_sensors = dbc.Table(children=[html.Tbody(rows)], bordered=True, hover=True, responsive=True)

    # Update depth graph
    depth = data.get('depth', {}).get('dpt', 0)
    depth_data.append(depth)
    depth_graph = {
        'data': [go.Scatter(x=list(range(len(depth_data))), y=list(depth_data), mode='lines', name='Depth (m)')],
        'layout': go.Layout(title='Depth Over Time', xaxis={'title': 'Time (s)'}, yaxis={'title': 'Depth (m)'}, template='plotly_dark')
    }

    return battery_display, formatted_thrusters, formatted_sensors, depth_graph