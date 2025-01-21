import json
from pathlib import Path

DATA_FILE = Path("data/data.json")


class JSONDataHandler:
    def __init__(self, file_path=DATA_FILE):
        self.file_path = file_path

    def read_data(self):
        """Reads and returns the data from the JSON file."""
        try:
            with open(self.file_path, "r") as json_file:
                return json.load(json_file)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"Error reading JSON file: {e}")
            return {}

    def get_section(self, section):
        """Fetches a specific section from the JSON file."""
        data = self.read_data()
        return data.get(section, {})

    def update_data(self, new_data):
        """Updates the JSON file with new data."""
        try:
            data = self.read_data()
            data.update(new_data)
            with open(self.file_path, "w") as json_file:
                json.dump(data, json_file, indent=4)
        except Exception as e:
            print(f"Error updating JSON file: {e}")
