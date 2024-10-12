import cv2
import socket
import numpy as np

# Backend server details
HOST = '127.0.0.1'
UDP_PORT = 65433

def open_video_stream():
    try:
        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        udp_socket.bind((HOST, UDP_PORT))

        print("Video stream window is now open.")
        while True:
            data, _ = udp_socket.recvfrom(8192)
            np_data = np.frombuffer(data, dtype=np.uint8)
            frame = cv2.imdecode(np_data, cv2.IMREAD_COLOR)

            if frame is not None:
                cv2.imshow('ROV Video Stream', frame)

            # Exit if 'q' is pressed
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

        udp_socket.close()
        cv2.destroyAllWindows()

    except Exception as e:
        print(f"Error receiving video stream: {e}")
