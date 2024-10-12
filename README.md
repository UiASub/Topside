Experimental frontend


FILE FORMAT

project-root/
├── app.py                 # Main Dash app
├── utils.py               # Contains backend connection and data fetch logic
├── callbacks.py           # Contains callback functions for updating the dashboard
├── components/            # Components directory
│   ├── __init__.py        # (Empty) to define it as a package
│   ├── battery.py         # Battery component
│   ├── thrusters.py       # Thrusters component
│   ├── sensors.py         # Sensors component
│   ├── lights.py          # Lights component
│   ├── depth.py           # Depth component
│   ├── video.py           # Video component


