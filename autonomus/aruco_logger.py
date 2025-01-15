import os
from datetime import datetime

ARUCO_LOG_FILE = f"logs/aruco_log_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.txt"
os.makedirs('logs', exist_ok=True)

class ArUcoLogger:
    def __init__(self, log_file=ARUCO_LOG_FILE):
        self.log_file = log_file
        self.logged_markers = set()

    def log_marker(self, marker_id):
        if marker_id not in self.logged_markers:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            log_entry = f"{timestamp} - Marker Detected: {marker_id}"
            with open(self.log_file, 'a') as file:
                file.write(log_entry + '\n')
            self.logged_markers.add(marker_id)
            print(f"Logged marker {marker_id}")
        else:
            print(f"Marker {marker_id} already logged.")
