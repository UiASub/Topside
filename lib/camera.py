import cv2
import numpy as np
from autonomus.image_proccesing import ArUcoMarkerDetector

def init_camera():
    """Initialize and return the default webcam."""
    camera = cv2.VideoCapture(0)
    return camera

def generate_frames(camera):
    # Replace these with your actual calibration parameters
    camera_matrix = np.array([
        [900, 0, 640],
        [0, 900, 360],
        [0, 0, 1]
    ], dtype=np.float32)
    dist_coeffs = np.zeros((5, 1), dtype=np.float32)

    detector = ArUcoMarkerDetector(camera_matrix=camera_matrix, dist_coeffs=dist_coeffs)

    while True:
        success, frame = camera.read()
        if not success:
            break

        # Detect and draw ArUco markers on the frame
        corners, ids, rejected = detector.detect_markers(frame)
        frame = detector.draw_detected_markers(frame, corners, ids)

        # Encode frame as JPEG
        ret, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()

        # Yield the frame for streaming
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')