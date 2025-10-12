import cv2
import numpy as np

# Dummy ArUco detector to keep code functional after removing autonomous
class DummyArUcoMarkerDetector:
    def __init__(self, camera_matrix=None, dist_coeffs=None):
        pass
    def detect_markers(self, frame):
        return [], [], []
    def draw_detected_markers(self, frame, corners, ids):
        return frame

def init_camera():
    """Initialize and return the default webcam."""
    camera = cv2.VideoCapture(0)
    return camera

def generate_frames(camera):
    camera_matrix = np.array([
        [900, 0, 640],
        [0, 900, 360],
        [0, 0, 1]
    ], dtype=np.float32)
    dist_coeffs = np.zeros((5, 1), dtype=np.float32)

    detector = DummyArUcoMarkerDetector(camera_matrix=camera_matrix, dist_coeffs=dist_coeffs)

    while True:
        success, frame = camera.read()
        if not success:
            break
        corners, ids, rejected = detector.detect_markers(frame)
        frame = detector.draw_detected_markers(frame, corners, ids)
        ret, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')