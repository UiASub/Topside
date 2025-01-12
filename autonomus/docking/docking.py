import cv2
import numpy as np
from autonomus.image_proccesing import ArUcoMarkerDetector


class AutonomousDocking:
    """Class for autonomous driving to a docking station."""

    def __init__(self, control_interface):
        """
        Initialize with a control interface.
        :param control_interface: Function to send commands to the ROV (e.g., {x, y, z, roll, yaw, pitch}).
        """
        self.detector = ArUcoMarkerDetector(
            camera_matrix=np.array([[1000, 0, 320], [0, 1000, 240], [0, 0, 1]], dtype=np.float32),
            dist_coeffs=np.zeros((5, 1), dtype=np.float32)
        )
        self.control_interface = control_interface

    def calculate_commands(self, rvec, tvec):
        """
        Calculate control commands based on relative position and orientation.
        :param rvec: Rotation vector from ArUco pose estimation.
        :param tvec: Translation vector from ArUco pose estimation.
        :return: Dictionary with control commands {x, y, z, roll, yaw, pitch}.
        """
        # Decompose rvec to yaw, pitch, roll (for simplicity, assuming yaw matters most)
        yaw = np.degrees(rvec[0][0][1])  # Extract yaw from rvec

        # Commands to center on the docking station
        x = int(-tvec[0][0][2] * 100)  # Forward/Backward proportional to Z distance
        y = int(tvec[0][0][0] * 100)  # Left/Right proportional to X distance
        z = int(tvec[0][0][1] * 100)  # Up/Down proportional to Y distance
        roll = 0  # Assume no roll adjustment needed
        pitch = 0  # Assume no pitch adjustment needed
        yaw = int(yaw / 10)  # Scale yaw for fine adjustments

        # Clip values to -100 to 100
        commands = {key: max(-100, min(100, value)) for key, value in
                    {"x": x, "y": y, "z": z, "roll": roll, "yaw": yaw, "pitch": pitch}.items()}
        return commands

    def run(self):
        """Main loop for autonomous docking."""
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            print("Error: Could not access camera.")
            return

        while True:
            ret, frame = cap.read()
            if not ret:
                print("Error: Could not read frame.")
                break

            # Detect ArUco markers
            corners, ids, _ = self.detector.detect_markers(frame)
            if ids is not None:
                for i, corner in enumerate(corners):
                    # Estimate pose
                    rvec, tvec, _ = cv2.aruco.estimatePoseSingleMarkers(corner, 0.05, self.detector.camera_matrix,
                                                                        self.detector.dist_coeffs)
                    # Draw detected markers
                    frame = self.detector.draw_detected_markers(frame, corners, ids)

                    # Calculate commands
                    commands = self.calculate_commands(rvec, tvec)
                    print(f"Commands: {commands}")

                    # Send commands to the ROV
                    self.control_interface(commands)
                    break  # Focus on the first detected marker for now

            # Display the frame
            cv2.imshow('Docking View', frame)

            # Stop on 'q' key press
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

        cap.release()
        cv2.destroyAllWindows()


# Example control interface
def dummy_control_interface(commands):
    """
    Dummy control interface for testing. Replace with actual ROV control code.
    :param commands: Dictionary with control commands {x, y, z, roll, yaw, pitch}.
    """
    print(f"Sending commands to ROV: {commands}")


if __name__ == "__main__":
    docking = AutonomousDocking(control_interface=dummy_control_interface)
    docking.run()
