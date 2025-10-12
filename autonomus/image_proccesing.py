import cv2
import numpy as np
from autonomus.aruco_logger import ArUcoLogger

aruco_logger = ArUcoLogger()

class ArUcoMarkerDetector:
    """Class for detecting ArUco markers with image preprocessing and drawing axes."""

    def __init__(self, aruco_type=cv2.aruco.DICT_6X6_250, camera_matrix=None, dist_coeffs=None):
        self.aruco_dict = cv2.aruco.getPredefinedDictionary(aruco_type)
        self.aruco_params = cv2.aruco.DetectorParameters()
        self.camera_matrix = camera_matrix
        self.dist_coeffs = dist_coeffs
        self.logger = ArUcoLogger()

    def preprocess_image(self, image):
        """Converts the image to grayscale and applies Gaussian blur for better detection."""
        gray_image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        blurred_image = cv2.GaussianBlur(gray_image, (5, 5), 0)
        return blurred_image

    def detect_markers(self, image):
        """Detects ArUco markers in the preprocessed image."""
        preprocessed_image = self.preprocess_image(image)
        corners, ids, rejected = cv2.aruco.detectMarkers(preprocessed_image, self.aruco_dict,
                                                         parameters=self.aruco_params)
        return corners, ids, rejected

    def draw_detected_markers(self, image, corners, ids):
        """Draws detected markers on the image and axes if camera parameters are provided."""
        if ids is not None:
            cv2.aruco.drawDetectedMarkers(image, corners, ids)
            print(f"Detected {len(ids)} marker(s): {ids.flatten()}")

            if self.camera_matrix is not None and self.dist_coeffs is not None:
                for corner in corners:
                    rvec, tvec, _ = cv2.aruco.estimatePoseSingleMarkers(corner, 0.05, self.camera_matrix,
                                                                        self.dist_coeffs)
                    cv2.drawFrameAxes(image, self.camera_matrix, self.dist_coeffs, rvec, tvec, 0.03)
        else:
            print("No markers detected.")
        return image

    def detect_markers(self, image):
        """Detects ArUco markers in the preprocessed image."""
        gray_image = self.preprocess_image(image)
        corners, ids, rejected = cv2.aruco.detectMarkers(gray_image, self.aruco_dict, parameters=self.aruco_params)
        if ids is not None:
            for marker_id in ids.flatten():
                self.logger.log_marker(marker_id)  # Log detected markers
        return corners, ids, rejected

    def display_image(self, image):
        """Displays the image with detected markers and axes."""
        cv2.imshow('Detected ArUco Markers with Axes', image)
        cv2.waitKey(0)
        cv2.destroyAllWindows()


def capture_image_from_webcam():
    """Captures an image from the webcam."""
    cap = cv2.VideoCapture(0)

    if not cap.isOpened():
        print("Error: Could not open webcam.")
        return None

    ret, frame = cap.read()
    if not ret:
        print("Error: Could not read frame from webcam.")
        cap.release()
        return None

    cap.release()
    return frame


if __name__ == "__main__":

    # Replace with your actual camera matrix and distortion coefficients
    camera_matrix = np.array([[1000, 0, 320], [0, 1000, 240], [0, 0, 1]], dtype=np.float32)  # Ensure float32 type
    dist_coeffs = np.zeros((5, 1), dtype=np.float32)  # Ensure float32 type

    # Example usage:
    if __name__ == "__main__":
        frame = capture_image_from_webcam()
        if frame is not None:
            detector = ArUcoMarkerDetector(camera_matrix=camera_matrix, dist_coeffs=dist_coeffs)
            corners, ids, rejected = detector.detect_markers(frame)
            frame_with_markers = detector.draw_detected_markers(frame, corners, ids)
            detector.display_image(frame_with_markers)
