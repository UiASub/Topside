import cv2

def init_camera():
    """Initialize and return the default webcam."""
    camera = cv2.VideoCapture(0)
    return camera

def generate_frames(camera):
    """
    Generator function that continuously reads frames from the provided camera
    and yields them as multipart/x-mixed-replace (MJPEG) for streaming.
    """
    while True:
        success, frame = camera.read()
        if not success:
            break
        else:
            # Encode frame as JPEG
            ret, buffer = cv2.imencode('.jpg', frame)
            frame = buffer.tobytes()

            # Yield a multipart response
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
