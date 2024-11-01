import socket
import base64
import cv2
import numpy as np
from lib.eventlogger import logger

# Backend server details
HOST = '127.0.0.1'
TCP_PORT = 65432  # Port for JSON data
UDP_PORT = 65433  # Port for video stream
UDP_BUFFER_SIZE = 2**16
    
# Function to fetch the video stream
def fetch_video_stream(app_video, udp_port=UDP_PORT, udp_buffer_size=UDP_BUFFER_SIZE) -> str:
    try:
        logger.log_info("Attempting to fetch video stream...")
        
        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        udp_socket.settimeout(None)
        udp_socket.bind(('0.0.0.0', udp_port))

        data, _ = udp_socket.recvfrom(udp_buffer_size)
        np_data = np.frombuffer(data, dtype=np.uint8)
        frame = cv2.imdecode(np_data, cv2.IMREAD_COLOR)
        
        if frame is None:
            logger.log_error("Failed to decode video stream frame.")
            return None

        _, buffer = cv2.imencode('.jpg', frame)
        video_base64 = base64.b64encode(buffer).decode('utf-8')

        logger.log_info("Video stream frame fetched and encoded successfully.")
        return video_base64

    except Exception as e:
        logger.log_error(f"Error receiving video stream: {e}")
        return None


def update_video(app_video):
    video_base64 = fetch_video_stream(app_video)
    if video_base64:
        logger.log_info("Video frame updated successfully in update_video.")
        return f'data:image/jpeg;base64,{video_base64}'
    
    logger.log_warning("No video frame available to update in update_video.")
    return ""
