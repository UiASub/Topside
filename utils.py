import socket
import json
import gzip
import struct
import cv2
import numpy as np
import base64

HOST = '127.0.0.1'
TCP_PORT = 65432
UDP_PORT = 65433

# Function to fetch JSON data from the backend
def fetch_json_data():
    try:
        print("Connecting to backend...")
        tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcp_socket.connect((HOST, TCP_PORT))
        print("Connected to backend")

        # Read data length (first 4 bytes)
        data_length = tcp_socket.recv(4)
        if not data_length:
            print("No data received.")
            return {}

        data_length = struct.unpack('>I', data_length)[0]
        print(f"Data length received: {data_length}")

        # Receive the actual data
        compressed_data = tcp_socket.recv(data_length)
        print(f"Compressed data received of length: {len(compressed_data)}")

        # Decompress and decode the JSON data
        json_data = gzip.decompress(compressed_data).decode('utf-8')
        data = json.loads(json_data)

        tcp_socket.close()
        return data
    except Exception as e:
        print(f"Error receiving JSON data: {e}")
        return {}


# Function to fetch video stream from the backend
def fetch_video_stream():
    try:
        print("Attempting to fetch video stream...")
        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        udp_socket.bind(('0.0.0.0', UDP_PORT))

        # Receive video stream data
        data, _ = udp_socket.recvfrom(8192)
        print(f"Received video stream of size {len(data)}")

        np_data = np.frombuffer(data, dtype=np.uint8)
        frame = cv2.imdecode(np_data, cv2.IMREAD_COLOR)

        # Encode the frame to base64
        _, buffer = cv2.imencode('.jpg', frame)
        return base64.b64encode(buffer).decode('utf-8')
    except Exception as e:
        print(f"Error receiving video stream: {e}")
        return None
