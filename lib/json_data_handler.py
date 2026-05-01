import json
import os
import threading
from pathlib import Path

from lib.runtime_paths import data_path

DATA_FILE = data_path("data.json")
_FILE_LOCKS = {}
_FILE_LOCKS_LOCK = threading.Lock()


def _lock_for(path: Path):
    key = path.resolve()
    with _FILE_LOCKS_LOCK:
        if key not in _FILE_LOCKS:
            _FILE_LOCKS[key] = threading.RLock()
        return _FILE_LOCKS[key]


class JSONDataHandler:
    def __init__(self, file_path=None):
        self.file_path = Path(file_path) if file_path is not None else data_path("data.json")
        self._lock = _lock_for(self.file_path)
        self._cached_data = {}
        self._last_error_log_ts = 0.0

    def read_data(self):
        """Reads and returns the data from the JSON file."""
        with self._lock:
            try:
                with open(self.file_path, "r") as json_file:
                    data = json.load(json_file)
                    if isinstance(data, dict):
                        self._cached_data = data
                    return data
            except (FileNotFoundError, json.JSONDecodeError) as e:
                # Avoid spamming logs on high-frequency polling.
                import time

                now = time.monotonic()
                if now - self._last_error_log_ts > 5.0:
                    print(f"Error reading JSON file {self.file_path}: {e}")
                    self._last_error_log_ts = now
                return self._cached_data

    def get_section(self, section):
        """Fetches a specific section from the JSON file."""
        data = self.read_data()
        return data.get(section, {})

    def update_data(self, new_data):
        """Updates the JSON file with new data."""
        with self._lock:
            try:
                data = self.read_data()
                data.update(new_data)
                self.file_path.parent.mkdir(parents=True, exist_ok=True)
                temp_file = self.file_path.with_name(f".{self.file_path.name}.tmp")
                with open(temp_file, "w") as json_file:
                    json.dump(data, json_file, indent=4)
                os.replace(temp_file, self.file_path)
            except Exception as e:
                print(f"Error updating JSON file {self.file_path}: {e}")
