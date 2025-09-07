"""
Tests for the bitmask converter module.
Tests the conversion between JSON and binary formats for STM32 communication.
"""

import sys
import os
import pytest
import json
import struct

# Add the parent directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../")))

from lib.bitmask_converter import BitmaskConverter, convert_json_to_binary, convert_binary_to_json


class TestBitmaskConverter:
    """Test suite for BitmaskConverter class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.converter = BitmaskConverter()
        
        # Sample JSON data matching the expected structure
        self.sample_json = {
            "Thrust": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
            "Buttons": {
                "button_surface": 1
            },
            "thrusters": {
                "U_FWD_P": {"power": 400, "temp": 20},
                "U_FWD_S": {"power": 420, "temp": 21},
                "U_AFT_P": {"power": 440, "temp": 22},
                "U_AFT_S": {"power": 460, "temp": 23}
            },
            "9dof": {
                "acceleration": {"x": 0.02, "y": -0.01, "z": 9.81},
                "gyroscope": {"x": 0.01, "y": 0.02, "z": 0.00},
                "magnetometer": {"x": 30.6, "y": -22.3, "z": 15.5}
            },
            "lights": {
                "Light1": 50,
                "Light2": 50,
                "Light3": 50,
                "Light4": 50
            },
            "battery": 100,
            "depth": {
                "dpt": 123,
                "dptSet": 124
            }
        }
    
    def test_initialization(self):
        """Test that the converter initializes correctly."""
        assert self.converter.struct_format.startswith('<')  # little-endian
        assert self.converter.struct_size > 0
        assert len(self.converter.DATA_MAPPING) > 0
    
    def test_get_binary_size(self):
        """Test getting the binary data size."""
        size = self.converter.get_binary_size()
        assert size > 0
        assert size == struct.calcsize(self.converter.struct_format)
    
    def test_get_format_string(self):
        """Test getting the format string."""
        format_str = self.converter.get_format_string()
        assert format_str.startswith('<')
        assert len(format_str) > 1
    
    def test_json_to_binary_basic(self):
        """Test basic JSON to binary conversion."""
        binary_data = self.converter.json_to_binary(self.sample_json)
        assert isinstance(binary_data, bytes)
        assert len(binary_data) == self.converter.struct_size
    
    def test_json_to_binary_empty_data(self):
        """Test JSON to binary conversion with empty data."""
        empty_json = {}
        binary_data = self.converter.json_to_binary(empty_json)
        assert isinstance(binary_data, bytes)
        assert len(binary_data) == self.converter.struct_size
    
    def test_json_to_binary_partial_data(self):
        """Test JSON to binary conversion with partial data."""
        partial_json = {
            "Thrust": [1.0, 2.0],  # Only 2 values instead of 6
            "battery": 75
        }
        binary_data = self.converter.json_to_binary(partial_json)
        assert isinstance(binary_data, bytes)
        assert len(binary_data) == self.converter.struct_size
    
    def test_binary_to_json_basic(self):
        """Test basic binary to JSON conversion."""
        # First convert JSON to binary
        binary_data = self.converter.json_to_binary(self.sample_json)
        
        # Then convert back to JSON
        reconstructed_json = self.converter.binary_to_json(binary_data)
        
        assert isinstance(reconstructed_json, dict)
        assert 'Thrust' in reconstructed_json
        assert 'Buttons' in reconstructed_json
        assert 'battery' in reconstructed_json
        assert 'depth' in reconstructed_json
    
    def test_binary_to_json_invalid_size(self):
        """Test binary to JSON conversion with invalid data size."""
        invalid_binary = b'too_short'
        with pytest.raises(ValueError, match="Binary data size"):
            self.converter.binary_to_json(invalid_binary)
    
    def test_round_trip_conversion(self):
        """Test complete round-trip conversion: JSON -> binary -> JSON."""
        # Convert to binary
        binary_data = self.converter.json_to_binary(self.sample_json)
        
        # Convert back to JSON
        reconstructed_json = self.converter.binary_to_json(binary_data)
        
        # Check key fields are preserved
        assert reconstructed_json['Thrust'][0] == self.sample_json['Thrust'][0]
        assert reconstructed_json['Thrust'][1] == self.sample_json['Thrust'][1]
        assert reconstructed_json['Buttons']['button_surface'] == self.sample_json['Buttons']['button_surface']
        assert reconstructed_json['battery'] == self.sample_json['battery']
        assert reconstructed_json['depth']['dpt'] == self.sample_json['depth']['dpt']
        assert reconstructed_json['depth']['dptSet'] == self.sample_json['depth']['dptSet']
    
    def test_thrust_values_preservation(self):
        """Test that thrust values are correctly preserved."""
        thrust_values = [10.5, -5.2, 0.0, 15.7, -8.1, 3.3]
        json_data = {"Thrust": thrust_values}
        
        binary_data = self.converter.json_to_binary(json_data)
        reconstructed = self.converter.binary_to_json(binary_data)
        
        for i, expected in enumerate(thrust_values):
            assert abs(reconstructed['Thrust'][i] - expected) < 0.001  # float precision
    
    def test_sensor_data_preservation(self):
        """Test that 9DOF sensor data is correctly preserved."""
        sensor_data = {
            "9dof": {
                "acceleration": {"x": 1.23, "y": -4.56, "z": 7.89},
                "gyroscope": {"x": 0.12, "y": 0.34, "z": -0.56},
                "magnetometer": {"x": 12.3, "y": -45.6, "z": 78.9}
            }
        }
        
        binary_data = self.converter.json_to_binary(sensor_data)
        reconstructed = self.converter.binary_to_json(binary_data)
        
        # Check acceleration values
        accel = reconstructed['9dof']['acceleration']
        assert abs(accel['x'] - 1.23) < 0.001
        assert abs(accel['y'] - (-4.56)) < 0.001
        assert abs(accel['z'] - 7.89) < 0.001
        
        # Check gyroscope values
        gyro = reconstructed['9dof']['gyroscope']
        assert abs(gyro['x'] - 0.12) < 0.001
        assert abs(gyro['y'] - 0.34) < 0.001
        assert abs(gyro['z'] - (-0.56)) < 0.001
    
    def test_thruster_averaging(self):
        """Test that thruster data is correctly averaged."""
        thruster_data = {
            "thrusters": {
                "T1": {"power": 100, "temp": 20},
                "T2": {"power": 200, "temp": 30},
                "T3": {"power": 300, "temp": 40}
            }
        }
        
        binary_data = self.converter.json_to_binary(thruster_data)
        reconstructed = self.converter.binary_to_json(binary_data)
        
        # Expected averages: power = 200, temp = 30
        avg_thruster = reconstructed['thrusters']['average']
        assert abs(avg_thruster['power'] - 200.0) < 0.001
        assert abs(avg_thruster['temp'] - 30.0) < 0.001
    
    def test_lights_averaging(self):
        """Test that lights data is correctly averaged."""
        lights_data = {
            "lights": {
                "Light1": 25,
                "Light2": 50,
                "Light3": 75,
                "Light4": 100
            }
        }
        
        binary_data = self.converter.json_to_binary(lights_data)
        reconstructed = self.converter.binary_to_json(binary_data)
        
        # Expected average: (25 + 50 + 75 + 100) / 4 = 62.5
        assert abs(reconstructed['lights']['average'] - 62.5) < 0.001


class TestConvenienceFunctions:
    """Test suite for convenience functions."""
    
    def test_convert_json_to_binary_dict(self):
        """Test convenience function with dict input."""
        json_data = {"battery": 85}
        binary_data = convert_json_to_binary(json_data)
        assert isinstance(binary_data, bytes)
        assert len(binary_data) > 0
    
    def test_convert_json_to_binary_string(self):
        """Test convenience function with JSON string input."""
        json_string = '{"battery": 85}'
        binary_data = convert_json_to_binary(json_string)
        assert isinstance(binary_data, bytes)
        assert len(binary_data) > 0
    
    def test_convert_binary_to_json(self):
        """Test convenience function for binary to JSON conversion."""
        json_data = {"battery": 85, "Thrust": [1, 2, 3, 4, 5, 6]}
        binary_data = convert_json_to_binary(json_data)
        
        reconstructed = convert_binary_to_json(binary_data)
        assert isinstance(reconstructed, dict)
        assert 'battery' in reconstructed
        assert 'Thrust' in reconstructed
    
    def test_convenience_round_trip(self):
        """Test round-trip conversion using convenience functions."""
        original_data = {
            "battery": 92,
            "Thrust": [1.1, 2.2, 3.3, 4.4, 5.5, 6.6],
            "Buttons": {"button_surface": 1}
        }
        
        # Convert to binary and back
        binary_data = convert_json_to_binary(original_data)
        reconstructed = convert_binary_to_json(binary_data)
        
        # Verify key values
        assert abs(reconstructed['battery'] - 92) < 0.001
        assert reconstructed['Buttons']['button_surface'] == 1
        assert abs(reconstructed['Thrust'][0] - 1.1) < 0.001


class TestEdgeCases:
    """Test suite for edge cases and error conditions."""
    
    def test_negative_values(self):
        """Test handling of negative values."""
        converter = BitmaskConverter()
        json_data = {
            "Thrust": [-1.0, -2.0, -3.0, -4.0, -5.0, -6.0],
            "9dof": {
                "acceleration": {"x": -9.81, "y": 0.0, "z": 0.0}
            }
        }
        
        binary_data = converter.json_to_binary(json_data)
        reconstructed = converter.binary_to_json(binary_data)
        
        # Check negative values are preserved
        assert reconstructed['Thrust'][0] < 0
        assert reconstructed['9dof']['acceleration']['x'] < 0
    
    def test_large_values(self):
        """Test handling of large values."""
        converter = BitmaskConverter()
        json_data = {
            "battery": 999.9,
            "Thrust": [1000.0, 2000.0, 3000.0, 4000.0, 5000.0, 6000.0]
        }
        
        binary_data = converter.json_to_binary(json_data)
        reconstructed = converter.binary_to_json(binary_data)
        
        # Values should be preserved (within float precision)
        assert abs(reconstructed['battery'] - 999.9) < 0.1
        assert abs(reconstructed['Thrust'][0] - 1000.0) < 0.1
    
    def test_zero_values(self):
        """Test handling of zero values."""
        converter = BitmaskConverter()
        json_data = {
            "Thrust": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "battery": 0,
            "Buttons": {"button_surface": 0}
        }
        
        binary_data = converter.json_to_binary(json_data)
        reconstructed = converter.binary_to_json(binary_data)
        
        # Zero values should be preserved
        assert all(abs(v) < 0.001 for v in reconstructed['Thrust'])
        assert abs(reconstructed['battery']) < 0.001
        assert reconstructed['Buttons']['button_surface'] == 0