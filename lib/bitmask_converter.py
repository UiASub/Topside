"""
Bitmask communication module for K2 Zephyr prototype.
Converts between JSON data and binary/packed data for STM32 microcontroller communication.
"""

import struct
import json
from typing import Dict, Any, Tuple, List, Union


class BitmaskConverter:
    """
    Handles conversion between JSON data and binary formats for STM32 communication.
    
    This class provides methods to pack JSON data into binary format using bitmasks
    and struct packing, and to unpack binary data back to JSON format.
    """
    
    # Define the data structure mapping for STM32 communication
    # Format: field_name -> (struct_format, default_value)
    DATA_MAPPING = {
        # Thrust values - 6 floats
        'thrust_x': ('f', 0.0),
        'thrust_y': ('f', 0.0), 
        'thrust_z': ('f', 0.0),
        'thrust_pitch': ('f', 0.0),
        'thrust_roll': ('f', 0.0),
        'thrust_yaw': ('f', 0.0),
        
        # Button states - packed as integers (bitmask)
        'button_surface': ('B', 0),  # unsigned char (0-255)
        
        # Thruster data - using representative values
        'thruster_power_avg': ('f', 0.0),  # average power
        'thruster_temp_avg': ('f', 0.0),   # average temperature
        
        # 9DOF sensor data
        'accel_x': ('f', 0.0),
        'accel_y': ('f', 0.0),
        'accel_z': ('f', 0.0),
        'gyro_x': ('f', 0.0),
        'gyro_y': ('f', 0.0),
        'gyro_z': ('f', 0.0),
        'mag_x': ('f', 0.0),
        'mag_y': ('f', 0.0),
        'mag_z': ('f', 0.0),
        
        # Lights - average value
        'lights_avg': ('f', 0.0),
        
        # Battery
        'battery': ('f', 0.0),
        
        # Depth
        'depth_current': ('f', 0.0),
        'depth_target': ('f', 0.0),
    }
    
    def __init__(self):
        """Initialize the converter with the data structure format."""
        # Create struct format string
        format_chars = [fmt for fmt, _ in self.DATA_MAPPING.values()]
        self.struct_format = '<' + ''.join(format_chars)  # little-endian
        self.struct_size = struct.calcsize(self.struct_format)
        
    def json_to_binary(self, json_data: Dict[str, Any]) -> bytes:
        """
        Convert JSON data to binary format for STM32 communication.
        
        Args:
            json_data: Dictionary containing sensor and control data
            
        Returns:
            bytes: Packed binary data ready for STM32 transmission
        """
        values = []
        
        # Extract thrust values
        thrust = json_data.get('Thrust', [0.0] * 6)
        if len(thrust) >= 6:
            values.extend(thrust[:6])
        else:
            values.extend(thrust + [0.0] * (6 - len(thrust)))
            
        # Extract button states
        buttons = json_data.get('Buttons', {})
        values.append(buttons.get('button_surface', 0))
        
        # Extract and average thruster data
        thrusters = json_data.get('thrusters', {})
        if thrusters:
            powers = [t.get('power', 0) for t in thrusters.values() if isinstance(t, dict)]
            temps = [t.get('temp', 0) for t in thrusters.values() if isinstance(t, dict)]
            avg_power = sum(powers) / len(powers) if powers else 0.0
            avg_temp = sum(temps) / len(temps) if temps else 0.0
        else:
            avg_power = avg_temp = 0.0
        values.extend([avg_power, avg_temp])
        
        # Extract 9DOF data
        dof_data = json_data.get('9dof', {})
        accel = dof_data.get('acceleration', {})
        gyro = dof_data.get('gyroscope', {})
        mag = dof_data.get('magnetometer', {})
        
        values.extend([
            accel.get('x', 0.0), accel.get('y', 0.0), accel.get('z', 0.0),
            gyro.get('x', 0.0), gyro.get('y', 0.0), gyro.get('z', 0.0),
            mag.get('x', 0.0), mag.get('y', 0.0), mag.get('z', 0.0)
        ])
        
        # Extract lights (average)
        lights = json_data.get('lights', {})
        if lights:
            light_values = [v for v in lights.values() if isinstance(v, (int, float))]
            avg_lights = sum(light_values) / len(light_values) if light_values else 0.0
        else:
            avg_lights = 0.0
        values.append(avg_lights)
        
        # Extract battery
        values.append(json_data.get('battery', 0.0))
        
        # Extract depth data
        depth = json_data.get('depth', {})
        values.extend([depth.get('dpt', 0.0), depth.get('dptSet', 0.0)])
        
        # Pack into binary format
        return struct.pack(self.struct_format, *values)
    
    def binary_to_json(self, binary_data: bytes) -> Dict[str, Any]:
        """
        Convert binary data back to JSON format.
        
        Args:
            binary_data: Packed binary data from STM32
            
        Returns:
            Dict: JSON-compatible dictionary structure
        """
        if len(binary_data) != self.struct_size:
            raise ValueError(f"Binary data size {len(binary_data)} doesn't match expected size {self.struct_size}")
            
        # Unpack binary data
        values = struct.unpack(self.struct_format, binary_data)
        
        # Reconstruct JSON structure
        json_data = {
            'Thrust': list(values[0:6]),
            'Buttons': {
                'button_surface': int(values[6])
            },
            'thrusters': {
                'average': {
                    'power': values[7],
                    'temp': values[8]
                }
            },
            '9dof': {
                'acceleration': {
                    'x': values[9],
                    'y': values[10], 
                    'z': values[11]
                },
                'gyroscope': {
                    'x': values[12],
                    'y': values[13],
                    'z': values[14]
                },
                'magnetometer': {
                    'x': values[15],
                    'y': values[16],
                    'z': values[17]
                }
            },
            'lights': {
                'average': values[18]
            },
            'battery': values[19],
            'depth': {
                'dpt': values[20],
                'dptSet': values[21]
            }
        }
        
        return json_data
    
    def get_binary_size(self) -> int:
        """Get the size of the binary data structure in bytes."""
        return self.struct_size
    
    def get_format_string(self) -> str:
        """Get the struct format string used for packing/unpacking."""
        return self.struct_format


def convert_json_to_binary(json_data: Union[Dict[str, Any], str]) -> bytes:
    """
    Convenience function to convert JSON data to binary format.
    
    Args:
        json_data: JSON data as dict or JSON string
        
    Returns:
        bytes: Binary data for STM32 communication
    """
    if isinstance(json_data, str):
        json_data = json.loads(json_data)
        
    converter = BitmaskConverter()
    return converter.json_to_binary(json_data)


def convert_binary_to_json(binary_data: bytes) -> Dict[str, Any]:
    """
    Convenience function to convert binary data to JSON format.
    
    Args:
        binary_data: Binary data from STM32
        
    Returns:
        Dict: JSON-compatible dictionary
    """
    converter = BitmaskConverter()
    return converter.binary_to_json(binary_data)