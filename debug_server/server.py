import socket
import cv2
import cv2.aruco as aruco
import struct
import json
import time
import gzip
import logging
import os
from threading import Thread, Event
import random
import traceback
from datetime import datetime

# Ensure the log directory exists
os.makedirs('/debug_server/server_logs', exist_ok=True)

# Configuration for logging
logging.basicConfig(
    filename=f"/debug_server/server_logs/log_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.txt",
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Configuration for the server
DEBUG_SERVER = True  # Run local server for testing providing video and sensor data
HOST = '127.0.0.1'    # Server IP
TCP_PORT = 65432      # TCP port for JSON data
UDP_PORT = 65433      # UDP port for video stream
JSON_FILE_PATH = 'debug_server/data.json'  # Path to JSON data

def log_error(error, context=""):
    """Log detailed error information with context."""
    logging.error(f"{context}: {error}")
    logging.debug(traceback.format_exc())  # Logs the full stack trace for in-depth debugging

def generate_random_json(data):
    # Randomize thruster power and temperature values
    for thruster in data['thrusters'].values():
        thruster['power'] = random.randint(400,600)
        thruster['temp'] = random.randint(15,30)
    # (Additional randomizations omitted for brevity)
    return data

def transmit_json_data(tcp_connection):
    """Transmit gzip-compressed JSON data over a TCP connection."""
    try:
        if not os.path.exists(JSON_FILE_PATH):
            logging.error(f"JSON file not found at {JSON_FILE_PATH}")
            return

        with open(JSON_FILE_PATH, 'r') as file:
            data = json.load(file)

        serialized_data = json.dumps(data).encode('utf-8')
        compressed_data = gzip.compress(serialized_data)
        data_length = struct.pack('>I', len(compressed_data))

        tcp_connection.sendall(data_length)
        tcp_connection.sendall(compressed_data)
        logging.info(f"Sent {len(compressed_data)} bytes of JSON data")

    except BrokenPipeError:
        logging.warning("Connection closed by the client during JSON transmission")
    except json.JSONDecodeError:
        log_error("Failed to decode JSON data", "JSON transmission")
    except Exception as error:
        log_error(error, "Error in JSON transmission")

def transmit_video_stream(udp_socket, udp_address, stop_event):
    """Capture video from webcam, detect ArUco markers, and transmit frames over UDP."""
    aruco_dict = aruco.getPredefinedDictionary(aruco.DICT_6X6_250)
    parameters = aruco.DetectorParameters()
    detector = aruco.ArucoDetector(aruco_dict, parameters)
    video_capture = cv2.VideoCapture(0)

    # Check if the video capture device is opened
    if not video_capture.isOpened():
        logging.error("Failed to open video capture device")
        return

    try:
        while not stop_event.is_set():
            start_time = time.time()

            ret, frame = video_capture.read()
            if not ret:
                break

            grayscale_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            corners, ids, _ = detector.detectMarkers(grayscale_frame)

            if ids is not None:
                frame = aruco.drawDetectedMarkers(frame, corners, ids)

            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 50]
            _, buffer = cv2.imencode('.jpg', frame, encode_param)

            if len(buffer) > 65507:
                logging.warning("Frame too large for UDP, skipping transmission")
                continue

            udp_socket.sendto(buffer.tobytes(), udp_address)

            elapsed_time = time.time() - start_time
            time.sleep(max(0, 0.03 - elapsed_time))

    except Exception as error:
        log_error(error, "Video transmission error")
    finally:
        video_capture.release()
        logging.info("Video stream capture and transmission ended")

def handle_client(tcp_connection, udp_socket, udp_address):
    """Handle client connection by transmitting JSON data and video stream in separate threads."""
    stop_event = Event()
    video_thread = Thread(target=transmit_video_stream, args=(udp_socket, udp_address, stop_event))
    video_thread.start()

    try:
        while not stop_event.is_set():
            transmit_json_data(tcp_connection)
            time.sleep(1)  # Adjust the frequency of JSON data updates as needed

    except ConnectionResetError:
        logging.warning("Connection reset by peer")
    except Exception as error:
        log_error(error, "Client handling error")
    finally:
        stop_event.set()  # Signal the video thread to terminate
        tcp_connection.close()
        logging.info("Connection closed")

def initiate_server():
    """Initialize the server to listen for incoming TCP connections and handle video and JSON data transmission."""
    tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        tcp_socket.bind((HOST, TCP_PORT))
        tcp_socket.listen(5)
        logging.info("TCP server listening...")

        while True:
            try:
                tcp_connection, address = tcp_socket.accept()
                logging.info(f"Connected to {address}")

                udp_address = (address[0], UDP_PORT)
                tcp_connection.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                client_thread = Thread(target=handle_client, args=(tcp_connection, udp_socket, udp_address))
                client_thread.start()

            except Exception as error:
                log_error(error, "Server error")
    finally:
        tcp_socket.close()
        udp_socket.close()
        logging.info("Sockets closed, server shutdown")

if __name__ == "__main__":
    initiate_server()
