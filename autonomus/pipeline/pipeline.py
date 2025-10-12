import cv2
import numpy as np
import logging
from cv2 import aruco

def initialize_video_capture():
    # Initialize video capture (replace with your video source)
    return cv2.VideoCapture(0)

def detect_pipeline(frame):
    # Convert frame to HSV color space
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    # Define yellow color range for pipeline detection
    lower_yellow = np.array([20, 100, 100])
    upper_yellow = np.array([30, 255, 255])

    # Create a mask for yellow color
    mask = cv2.inRange(hsv, lower_yellow, upper_yellow)

    # Find contours in the mask
    contours, _ = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    # Assume the largest contour is the pipeline
    if contours:
        largest_contour = max(contours, key=cv2.contourArea)
        return largest_contour
    return None

def detect_aruco_markers(frame):
    # Load the ArUco dictionary
    aruco_dict = aruco.Dictionary_get(aruco.DICT_6X6_250)
    parameters = aruco.DetectorParameters_create()

    # Detect markers
    corners, ids, _ = aruco.detectMarkers(frame, aruco_dict, parameters=parameters)

    # Draw detected markers
    if ids is not None:
        aruco.drawDetectedMarkers(frame, corners, ids)
        return ids.flatten()
    return []

def follow_pipeline():
    logging.info("Pipeline following mode activated.")
    cap = initialize_video_capture()

    while True:
        ret, frame = cap.read()
        if not ret:
            logging.error("Failed to capture video frame.")
            break

        # Detect pipeline
        pipeline_contour = detect_pipeline(frame)
        if pipeline_contour is not None:
            cv2.drawContours(frame, [pipeline_contour], -1, (0, 255, 0), 3)
            logging.info("Pipeline detected.")

        # Detect ArUco markers
        marker_ids = detect_aruco_markers(frame)
        if marker_ids:
            logging.info(f"Detected ArUco markers: {marker_ids}")

        # Display the processed frame
        cv2.imshow('Pipeline Following', frame)

        # Break the loop if 'q' is pressed
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

def stop_following_pipeline():
    logging.info("Pipeline following mode deactivated.")
    # Add logic to stop the pipeline-following behavior
    pass