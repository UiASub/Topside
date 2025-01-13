import socket
import json
import struct
import gzip
from lib.eventlogger import logger

# Backend server details
HOST = '127.0.0.1'
TCP_PORT = 65432
UDP_PORT = 65433

def test_backend_connection():
    try:
        tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcp_socket.connect((HOST, TCP_PORT))
        print("Connection to backend successful")
        logger.log_info("Connection to backend successful")
        tcp_socket.close()
    except Exception as e:
        print(f"Error connecting to backend: {e}")
        logger.log_error(f"Error connecting to backend: {e}")

# Fetch JSON data from backend (as in old frontend)
def fetch_json_data():
    try:
        print("Attempting to fetch JSON data...")
        logger.log_info("Attempting to fetch JSON data...")
        
        tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcp_socket.connect((HOST, TCP_PORT))

        # Read data length (first 4 bytes)
        data_length = tcp_socket.recv(4)
        if not data_length:
            print("No data received.")
            logger.log_warning("No data received from backend")
            return {}

        # Unpack the length of the compressed data
        data_length = struct.unpack('>I', data_length)[0]

        # Receive the actual data
        compressed_data = tcp_socket.recv(data_length)

        # Decompress the data
        json_data = gzip.decompress(compressed_data).decode('utf-8')

        # Parse the JSON data
        data = json.loads(json_data)

        tcp_socket.close()
        print("JSON data received successfully")
        logger.log_info("JSON data received successfully")
        return data

    except Exception as e:
        print(f"Error receiving JSON data: {e}")
        logger.log_error(f"Error receiving JSON data: {e}")
        return {}