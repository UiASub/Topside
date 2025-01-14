import cv2
import numpy as np
import glob

"""
Dette scriptet kjøres for å kalibrere kameraet for best mulig aruco detection resultat, bruk sjakkmønstefilen vedlagt for kalibrering. Spør Storm ved flere spørsmål

Mer info her: https://docs.opencv.org/4.x/dc/dbb/tutorial_py_calibration.html
"""


def calibrate_camera(images_path, pattern_size=(9, 6), square_size=1.0):
    """
    Calibrate the camera using images of a chessboard pattern.

    :param images_path: Path to the images of the chessboard.
    :param pattern_size: The number of internal corners per a chessboard row and column (e.g., (9, 6)).
    :param square_size: The size of a single square in your chessboard in a unit (e.g., 1.0 cm or 1.0 m).
    :return: Camera matrix and distortion coefficients.
    """
    # Termination criteria for corner sub-pixel refinement
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)

    # Prepare object points (3D points in real world space)
    objp = np.zeros((np.prod(pattern_size), 3), np.float32)
    objp[:, :2] = np.indices(pattern_size).T.reshape(-1, 2)
    objp *= square_size

    # Arrays to store object points and image points
    objpoints = []  # 3D points in real-world space
    imgpoints = []  # 2D points in image plane

    # Read all images from the folder
    images = glob.glob(f"{images_path}/*.jpg")
    if not images:
        print("No images found in the specified path.")
        return None, None

    for fname in images:
        img = cv2.imread(fname)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Find the chessboard corners
        ret, corners = cv2.findChessboardCorners(gray, pattern_size, None)

        if ret:
            objpoints.append(objp)
            corners2 = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
            imgpoints.append(corners2)

            # Draw and display the corners for visualization (optional)
            img = cv2.drawChessboardCorners(img, pattern_size, corners2, ret)
            cv2.imshow('Chessboard', img)
            cv2.waitKey(500)

    cv2.destroyAllWindows()

    # Perform camera calibration
    ret, camera_matrix, dist_coeffs, rvecs, tvecs = cv2.calibrateCamera(objpoints, imgpoints, gray.shape[::-1], None,
                                                                        None)

    if ret:
        print("Camera calibration successful.")
        print("Camera Matrix:")
        print(camera_matrix)
        print("Distortion Coefficients:")
        print(dist_coeffs)
    else:
        print("Camera calibration failed.")

    return camera_matrix, dist_coeffs


# Call the function with the path to your images
images_path = "autonomus/calibration/calibration_image.png"
camera_matrix, dist_coeffs = calibrate_camera(images_path)
