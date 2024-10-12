from dash.dependencies import Input, Output
from app import app
from utils import fetch_json_data, fetch_video_stream
from collections import deque
import plotly.graph_objs as go

depth_data = deque(maxlen=50)  # For depth graph

# Update battery, thrusters, sensors, lights, depth data
@app.callback(
    [Output('battery-display', 'children'),
     Output('thruster-table', 'children'),
     Output('sensor-table', 'children'),
     Output('lights-display', 'children'),
     Output('depth-graph', 'figure')],
    [Input('json-interval', 'n_intervals')]
)
def update_json_data(n_intervals):
    data = fetch_json_data()

    # Battery display
    battery_display = f"Battery: {data.get('battery', 0)} %"

    # Thrusters display
    thrusters = data.get('thrusters', {})
    thruster_table = html.Table([
        html.Thead(html.Tr([html.Th("Thruster"), html.Th("Power (W)"), html.Th("Temperature (°C)")]))
    ] + [
        html.Tr([html.Td(k), html.Td(v['power']), html.Td(v['temp'])]) for k, v in thrusters.items()
    ])

    # 9DOF sensor data
    sensors = data.get('9dof', {})
    sensor_table = html.Table([
        html.Tr([html.Th("Acceleration"), html.Td(f"x: {sensors['acceleration']['x']}"),
                                   html.Td(f"y: {sensors['acceleration']['y']}"),
                                   html.Td(f"z: {sensors['acceleration']['z']}")]),
        html.Tr([html.Th("Gyroscope"), html.Td(f"x: {sensors['gyroscope']['x']}"),
                                 html.Td(f"y: {sensors['gyroscope']['y']}"),
                                 html.Td(f"z: {sensors['gyroscope']['z']}")]),
        html.Tr([html.Th("Magnetometer"), html.Td(f"x: {sensors['magnetometer']['x']}"),
                                     html.Td(f"y: {sensors['magnetometer']['y']}"),
                                     html.Td(f"z: {sensors['magnetometer']['z']}")]),
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


# Update video stream
@app.callback(
    Output('video-stream', 'src'),
    [Input('video-interval', 'n_intervals')]
)
def update_video_stream(n_intervals):
    video_base64 = fetch_video_stream()
    if video_base64:
        return f'data:image/jpeg;base64,{video_base64}'
    return ""
