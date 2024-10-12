from dash.dependencies import Input, Output
from app import app
from utils import fetch_json_data
from dash import html
from collections import deque
import plotly.graph_objs as go

depth_data = deque(maxlen=50)

# Update dashboard data from backend
@app.callback(
    [Output('battery-display', 'children'),
     Output('thruster-table', 'children'),
     Output('sensor-table', 'children'),
     Output('lights-display', 'children'),
     Output('depth-graph', 'figure')],
    [Input('json-interval', 'n_intervals')]
)
def update_json_data(n_intervals):
    print(f"Update triggered at interval: {n_intervals}")
    data = fetch_json_data()

    # Log the fetched data to ensure it is correctly received
    print(f"Fetched data: {data}")

    # Battery display
    battery_display = f"Battery: {data.get('battery', 0)} %"

    # Thrusters display
    thrusters = data.get('thrusters', {})
    thruster_table = html.Table([
        html.Thead(html.Tr([html.Th("Thruster"), html.Th("Power (W)"), html.Th("Temperature (°C)")]))
    ] + [
        html.Tr([html.Td(k), html.Td(f"Power: {v['power']}W"), html.Td(f"Temp: {v['temp']}°C")]) for k, v in thrusters.items()
    ])

    # 9DOF sensor data
    sensors = data.get('9dof', {})
    sensor_table = html.Table([
        html.Tr([html.Td("Acceleration"), html.Td(f"x: {sensors['acceleration']['x']}"), html.Td(f"y: {sensors['acceleration']['y']}"), html.Td(f"z: {sensors['acceleration']['z']}")]),
        html.Tr([html.Td("Gyroscope"), html.Td(f"x: {sensors['gyroscope']['x']}"), html.Td(f"y: {sensors['gyroscope']['y']}"), html.Td(f"z: {sensors['gyroscope']['z']}")]),
        html.Tr([html.Td("Magnetometer"), html.Td(f"x: {sensors['magnetometer']['x']}"), html.Td(f"y: {sensors['magnetometer']['y']}"), html.Td(f"z: {sensors['magnetometer']['z']}")])
    ])

    # Lights display
    lights = data.get('lights', {})
    lights_display = html.Ul([html.Li(f"Light {i}: {lights.get(f'Light{i}', 0)} %") for i in range(1, 5)])

    # Depth graph
    depth = data.get('depth', {}).get('dpt', 0)
    depth_data.append(depth)
    depth_graph = {
        'data': [go.Scatter(x=list(range(len(depth_data))), y=list(depth_data), mode='lines', name='Depth (m)')],
        'layout': go.Layout(title='Depth Over Time', xaxis={'title': 'Time (s)'}, yaxis={'title': 'Depth (m)'}, template='plotly_dark')
    }

    return battery_display, thruster_table, sensor_table, lights_display, depth_graph
