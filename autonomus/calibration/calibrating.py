import numpy as np
import cv2 as cv
import glob
import os

# Termination criteria for corner refinement
criteria = (cv.TERM_CRITERIA_EPS + cv.TERM_CRITERIA_MAX_ITER, 30, 0.001)

# Prepare object points based on correct grid size (9x6 internal corners)
objp = np.zeros((9 * 6, 3), np.float32)
objp[:, :2] = np.mgrid[0:9, 0:6].T.reshape(-1, 2)

# Arrays to store object points and image points
objpoints = []  # 3D points in real-world space
imgpoints = []  # 2D points in the image plane

# Define correct path for calibration images
image_dir = os.path.join(os.path.dirname(__file__), 'calibration_images')
image_pattern = os.path.join(image_dir, '*.jpg')

# Load calibration images
images = glob.glob(image_pattern)

if not images:
    print(f"No images found in directory: {image_dir}. Please check the path and filenames.")
    exit()

for fname in images:
    img = cv.imread(fname)
    if img is None:
        print(f"Failed to load image: {fname}")
        continue

    gray = cv.cvtColor(img, cv.COLOR_BGR2GRAY)

    # Find the chessboard corners (using correct 9x6 pattern)
    ret, corners = cv.findChessboardCorners(gray, (9, 6), None)

    if ret:
        objpoints.append(objp)

        # Refine detected corners
        corners2 = cv.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
        imgpoints.append(corners2)

        # Draw and display the corners
        cv.drawChessboardCorners(img, (9, 6), corners2, ret)
        cv.imshow('Calibration Image', img)
        cv.waitKey(500)
    else:
        print(f"Chessboard corners not found in: {fname}")

cv.destroyAllWindows()

# Check if enough valid patterns were detected
if len(objpoints) > 0:
    # Perform camera calibration using the last valid grayscale shape
    img_shape = gray.shape[::-1]
    ret, mtx, dist, rvecs, tvecs = cv.calibrateCamera(objpoints, imgpoints, img_shape, None, None)

    # Save calibration results
    np.savez(os.path.join(image_dir, "camera_calibration_data.npz"), camera_matrix=mtx, dist_coeffs=dist)

    print("Calibration successful!")
    print("Camera Matrix:\n", mtx)
    print("Distortion Coefficients:\n", dist)

    # Test undistortion
    test_img_path = images[0]  # Use the first image for testing
    test_img = cv.imread(test_img_path)
    h, w = test_img.shape[:2]
    newcameramtx, roi = cv.getOptimalNewCameraMatrix(mtx, dist, (w, h), 1, (w, h))

    # Apply undistortion
    dst = cv.undistort(test_img, mtx, dist, None, newcameramtx)

    # Crop and save the undistorted image
    x, y, w, h = roi
    dst = dst[y:y + h, x:x + w]
    undistorted_img_path = os.path.join(image_dir, 'undistorted_result.png')
    cv.imwrite(undistorted_img_path, dst)

    print(f"Undistorted image saved as '{undistorted_img_path}'")

else:
    print("No valid images found with detectable chessboard corners. Calibration aborted.")
