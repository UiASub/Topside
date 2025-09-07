#!/usr/bin/env python3
"""
Demo script for bitmask communication with K2 Zephyr prototype.
Demonstrates JSON to binary conversion for STM32 microcontroller communication.
"""

import json
import sys
import os

# Add the parent directory to sys.path to import our modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lib.bitmask_converter import BitmaskConverter, convert_json_to_binary, convert_binary_to_json
from lib.json_data_handler import JSONDataHandler


def demo_basic_conversion():
    """Demonstrate basic JSON to binary conversion and back."""
    print("=== Basic Bitmask Conversion Demo ===")
    
    # Sample JSON data similar to what the system uses
    sample_data = {
        "Thrust": [10.5, -5.2, 0.0, 15.7, -8.1, 3.3],
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
            "Light2": 60,
            "Light3": 70,
            "Light4": 80
        },
        "battery": 92.5,
        "depth": {
            "dpt": 123.4,
            "dptSet": 125.0
        }
    }
    
    print("Original JSON data:")
    print(json.dumps(sample_data, indent=2))
    
    # Convert to binary
    binary_data = convert_json_to_binary(sample_data)
    print(f"\nBinary data size: {len(binary_data)} bytes")
    print(f"Binary data (hex): {binary_data.hex()}")
    
    # Convert back to JSON
    reconstructed_data = convert_binary_to_json(binary_data)
    print("\nReconstructed JSON data:")
    print(json.dumps(reconstructed_data, indent=2))
    
    # Show the compression ratio
    json_size = len(json.dumps(sample_data).encode('utf-8'))
    binary_size = len(binary_data)
    compression_ratio = json_size / binary_size
    print(f"\nCompression ratio: {compression_ratio:.2f}x")
    print(f"JSON size: {json_size} bytes")
    print(f"Binary size: {binary_size} bytes")
    print(f"Space saved: {json_size - binary_size} bytes ({((json_size - binary_size) / json_size * 100):.1f}%)")


def demo_converter_details():
    """Show detailed information about the converter."""
    print("\n=== Converter Details ===")
    
    converter = BitmaskConverter()
    print(f"Struct format: {converter.get_format_string()}")
    print(f"Binary data size: {converter.get_binary_size()} bytes")
    print(f"Data mapping fields: {len(converter.DATA_MAPPING)}")
    
    print("\nData field mapping:")
    for i, (field, (fmt, default)) in enumerate(converter.DATA_MAPPING.items()):
        print(f"  {i:2d}. {field:20} -> {fmt:2} (default: {default})")


def demo_real_data():
    """Demonstrate conversion using real data from the system."""
    print("\n=== Real System Data Demo ===")
    
    try:
        # Try to read from the actual data file
        data_handler = JSONDataHandler()
        real_data = data_handler.read_data()
        
        if real_data:
            print("Real system data:")
            print(json.dumps(real_data, indent=2))
            
            # Convert to binary
            binary_data = convert_json_to_binary(real_data)
            print(f"\nBinary representation: {len(binary_data)} bytes")
            
            # Convert back
            reconstructed = convert_binary_to_json(binary_data)
            print(f"\nReconstructed data preview:")
            print(f"  Battery: {reconstructed.get('battery', 'N/A')}")
            print(f"  Thrust: {reconstructed.get('Thrust', 'N/A')}")
            if '9dof' in reconstructed:
                accel = reconstructed['9dof']['acceleration']
                print(f"  Acceleration: x={accel['x']:.3f}, y={accel['y']:.3f}, z={accel['z']:.3f}")
        else:
            print("No real data available (data.json might be empty)")
            
    except Exception as e:
        print(f"Could not read real system data: {e}")


def demo_stm32_compatibility():
    """Demonstrate STM32 compatibility aspects."""
    print("\n=== STM32 Compatibility Demo ===")
    
    converter = BitmaskConverter()
    
    # Show data types used
    print("Data types used (STM32 compatible):")
    print("  'f' -> float (32-bit IEEE 754)")
    print("  'B' -> unsigned char (8-bit, 0-255)")
    
    # Show byte order
    print(f"\nByte order: Little-endian ('<')")
    print(f"Total struct size: {converter.get_binary_size()} bytes")
    
    # Example of what STM32 would receive
    sample_data = {
        "Thrust": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
        "battery": 100.0,
        "Buttons": {"button_surface": 1}
    }
    
    binary = convert_json_to_binary(sample_data)
    print(f"\nExample binary data for STM32:")
    print(f"Hex: {binary.hex()}")
    print(f"Bytes: {list(binary)}")
    
    # Show how to unpack in C-style
    print(f"\nC struct equivalent:")
    print("typedef struct {")
    print("    float thrust[6];      // 6 * 4 = 24 bytes")
    print("    uint8_t button_surface; // 1 byte")  
    print("    float thruster_power_avg; // 4 bytes")
    print("    float thruster_temp_avg;  // 4 bytes")
    print("    float accel[3];       // 3 * 4 = 12 bytes")
    print("    float gyro[3];        // 3 * 4 = 12 bytes") 
    print("    float mag[3];         // 3 * 4 = 12 bytes")
    print("    float lights_avg;     // 4 bytes")
    print("    float battery;        // 4 bytes")
    print("    float depth_current;  // 4 bytes")
    print("    float depth_target;   // 4 bytes")
    print(f"}} sensor_data_t; // Total: {converter.get_binary_size()} bytes")


if __name__ == "__main__":
    print("Bitmask Communication Demo for K2 Zephyr Prototype")
    print("=" * 50)
    
    try:
        demo_basic_conversion()
        demo_converter_details()
        demo_real_data()
        demo_stm32_compatibility()
        
        print("\n" + "=" * 50)
        print("Demo completed successfully!")
        print("\nThe bitmask converter is ready for STM32 communication.")
        print("Use the functions in lib.comms for actual transmission:")
        print("  - send_bitmask_data_to_stm32()")
        print("  - receive_bitmask_data_from_stm32()")
        print("  - send_bitmask_data_continuous()")
        
    except Exception as e:
        print(f"\nDemo failed with error: {e}")
        sys.exit(1)