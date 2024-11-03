import socket
import cv2
import cv2.aruco as aruco
import struct
import json
import time
import gzip
from threading import Thread
import random

# Configuration
DEBUG_SERVER = True # Run local server for testing providing video and sensor data
HOST = '127.0.0.1'  # Server IP
TCP_PORT = 65432  # TCP port for JSON data
UDP_PORT = 65433  # UDP port for video stream
JSON_FILE_PATH = 'debug_server/data.json'  # Path to JSON data

def generate_random_json(data):
    #Randomize thruster power and temperature values
    for thruster in data['thrusters'].values():
        thruster['power'] = random.randint(400,600)
        thruster['temp'] = random.randint(15,30)

    # Randomize 9dof (acceleration, gyroscope, and magnetometer)
    data['9dof']['acceleration']['x'] = round(random.uniform(-0.05, 0.05), 2)
    data['9dof']['acceleration']['y'] = round(random.uniform(-0.05, 0.05), 2)
    data['9dof']['acceleration']['z'] = round(random.uniform(9.7, 9.9), 2)

    data['9dof']['gyroscope']['x'] = round(random.uniform(-0.05, 0.05), 2)
    data['9dof']['gyroscope']['y'] = round(random.uniform(-0.05, 0.05), 2)
    data['9dof']['gyroscope']['z'] = round(random.uniform(-0.05, 0.05), 2)

    data['9dof']['magnetometer']['x'] = round(random.uniform(25.0, 35.0), 1)
    data['9dof']['magnetometer']['y'] = round(random.uniform(-25.0, -20.0), 1)
    data['9dof']['magnetometer']['z'] = round(random.uniform(10.0, 20.0), 1)

    # Randomize light intesity and battery level
    for light in data['lights'].keys():
        data['lights'][light] = random.randint(0,100)

    data['battery'] = random.randint(50,100)

    # Randomize depth
    data['depth']['dpt'] = random.randint(100,150)
    data['depth']['dptset'] = data['depth']['dpt']

    return data

def transmit_json_data(tcp_connection):
    """
    Transmit gzip-compressed JSON data over a TCP connection.
    """
    try:
        with open(JSON_FILE_PATH, 'r') as file:
            data = json.load(file)

        serialized_data = json.dumps(data).encode('utf-8')
        compressed_data = gzip.compress(serialized_data)  # Use gzip for compression now
        data_length = struct.pack('>I', len(compressed_data))  # Pack the length of the data

        tcp_connection.sendall(data_length)  # Send length first
        tcp_connection.sendall(compressed_data)  # Send the compressed data
        print(f"Sent {len(compressed_data)} bytes of JSON data")

    except BrokenPipeError:
        print("Connection closed by the client")
    except Exception as error:
        print(f"Error in JSON transmission: {error}")


def transmit_video_stream(udp_socket, udp_address):
    """
    Capture video from webcam, detect ArUco markers, and transmit frames over UDP.
    """
    aruco_dict = aruco.getPredefinedDictionary(aruco.DICT_6X6_250)
    parameters = aruco.DetectorParameters()
    parameters.adaptiveThreshWinSizeMin = 3
    parameters.adaptiveThreshWinSizeMax = 23
    parameters.adaptiveThreshWinSizeStep = 10
    parameters.minMarkerPerimeterRate = 0.04
    parameters.maxMarkerPerimeterRate = 1.0
    parameters.polygonalApproxAccuracyRate = 0.03
    parameters.cornerRefinementMethod = aruco.CORNER_REFINE_SUBPIX

    detector = aruco.ArucoDetector(aruco_dict, parameters)
    video_capture = cv2.VideoCapture(0)

    try:
        while True:
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

            udp_socket.sendto(buffer.tobytes(), udp_address)

            elapsed_time = time.time() - start_time
            time.sleep(max(0, 0.03 - elapsed_time))  # Targeting ~30 FPS

    except Exception as error:
        print(f"Video transmission error: {error}")
    finally:
        video_capture.release()

def handle_client(tcp_connection, udp_socket, udp_address):
    """
    Handle client connection by transmitting JSON data and video stream in separate threads.
    """
    video_thread = Thread(target=transmit_video_stream, args=(udp_socket, udp_address))
    video_thread.start()

    try:
        while True:
            transmit_json_data(tcp_connection)
            time.sleep(1)  # Adjust the frequency of JSON data updates as needed

    except Exception as error:
        print(f"Client handling error: {error}")
    finally:
        tcp_connection.close()
        print("Connection closed")

def initiate_server():
    """
    Initialize the server to listen for incoming TCP connections and handle video and JSON data transmission.
    """
    # Setup TCP socket for JSON data transmission
    tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)  # Enable TCP keep-alive
    tcp_socket.bind((HOST, TCP_PORT))
    tcp_socket.listen(5)  # Listen for up to 5 clients
    print("TCP server listening...")

    # Setup UDP socket for video stream transmission
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    while True:
        try:
            tcp_connection, address = tcp_socket.accept()
            print(f"Connected to {address}")

            udp_address = (address[0], UDP_PORT)
            tcp_connection.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)  # Enable keep-alive for connection
            client_thread = Thread(target=handle_client, args=(tcp_connection, udp_socket, udp_address))
            client_thread.start()

        except Exception as error:
            print(f"Server error: {error}")

if __name__ == "__main__":
    initiate_server()
