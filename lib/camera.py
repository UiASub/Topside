import cv2
import numpy as np
import threading
import subprocess
import shutil
import time

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


class RPiCameraReceiver:
    """Receives RTP/H264 stream from Raspberry Pi and exposes latest JPEG frame."""

    def __init__(
        self,
        host="0.0.0.0",
        port=6969,
        latency_ms=12,
        out_width=960,
        out_height=540,
        jpeg_quality=70,
        flip_180=False,
    ):
        self.host = host
        self.port = int(port)
        self.latency_ms = max(0, int(latency_ms))
        self.out_width = max(160, int(out_width))
        self.out_height = max(120, int(out_height))
        self.jpeg_quality = min(95, max(40, int(jpeg_quality)))
        self.flip_180 = bool(flip_180)
        self.is_connected = False
        self.is_listening = False
        self.backend = "none"
        self.last_error = None

        self._stop_event = threading.Event()
        self._thread = None
        self._cap = None
        self._gst_proc = None
        self._stderr_thread = None

        self._frame_lock = threading.Lock()
        self._frame_cond = threading.Condition(self._frame_lock)
        self._latest_jpeg = None
        self._frame_seq = 0
        self._last_frame_ts = 0.0
        self._placeholder_jpeg = self._build_placeholder_jpeg()

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._cleanup()

    def get_latest_jpeg(self):
        with self._frame_lock:
            return self._latest_jpeg

    def get_latest_jpeg_and_seq(self):
        with self._frame_lock:
            return self._latest_jpeg, self._frame_seq

    def wait_for_next_frame(self, last_seq, timeout=0.25):
        with self._frame_cond:
            if self._frame_seq == last_seq:
                self._frame_cond.wait(timeout=timeout)
            return self._latest_jpeg, self._frame_seq

    def get_placeholder_jpeg(self):
        return self._placeholder_jpeg

    def get_status(self):
        age_ms = None
        if self._last_frame_ts > 0:
            age_ms = int((time.monotonic() - self._last_frame_ts) * 1000)
        return {
            "connected": bool(self.is_connected),
            "listening": bool(self.is_listening),
            "backend": self.backend,
            "port": self.port,
            "latency_ms": self.latency_ms,
            "out_width": self.out_width,
            "out_height": self.out_height,
            "jpeg_quality": self.jpeg_quality,
            "flip_180": self.flip_180,
            "last_frame_age_ms": age_ms,
            "last_error": self.last_error,
        }

    def _set_frame(self, frame):
        ok, buf = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        if not ok:
            return
        self._set_jpeg_bytes(buf.tobytes())

    def _set_jpeg_bytes(self, jpg):
        with self._frame_cond:
            self._latest_jpeg = jpg
            self._frame_seq += 1
            self._frame_cond.notify_all()
        self._last_frame_ts = time.monotonic()
        self.is_connected = True

    def _build_placeholder_jpeg(self):
        blank = np.zeros((720, 1280, 3), dtype=np.uint8)
        cv2.putText(blank, "WAITING FOR RPI CAMERA STREAM", (280, 360),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 222, 255), 2, cv2.LINE_AA)
        ok, buf = cv2.imencode('.jpg', blank, [int(cv2.IMWRITE_JPEG_QUALITY), 75])
        return buf.tobytes() if ok else b""

    def _run(self):
        print("[RPi Camera] Trying OpenCV+GStreamer …")
        if self._opencv_gstreamer_available():
            if self._run_opencv_gstreamer():
                return
        else:
            print("[RPi Camera]   OpenCV has no GStreamer support, skipping.")

        print("[RPi Camera] Trying gst-launch-1.0 …")
        self._run_gst_subprocess()

    def _opencv_gstreamer_available(self):
        try:
            return "GStreamer:                   YES" in cv2.getBuildInformation()
        except Exception:
            return False

    def _run_opencv_gstreamer(self):
        self.backend = "opencv-gstreamer"
        videoflip_stage = "! videoflip method=rotate-180 " if self.flip_180 else ""
        pipeline = (
            f"udpsrc address={self.host} port={self.port} "
            "caps=application/x-rtp,media=video,encoding-name=H264,payload=96,clock-rate=90000 "
            f"! rtpjitterbuffer latency={self.latency_ms} drop-on-latency=true "
            "! rtph264depay ! h264parse ! avdec_h264 ! videoconvert "
            f"{videoflip_stage}"
            f"! videoscale ! video/x-raw,width={self.out_width},height={self.out_height} "
            "! appsink drop=1 max-buffers=1 sync=false"
        )

        cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
        self._cap = cap
        if not cap.isOpened():
            self.last_error = "OpenCV GStreamer pipeline failed to open"
            return False

        print(f"[RPi Camera]   Listening on UDP port {self.port} …")
        self.is_listening = True
        had_frame = False
        while not self._stop_event.is_set():
            ok, frame = cap.read()
            if ok and frame is not None and frame.size > 0:
                if not had_frame:
                    print("[RPi Camera] ✓ Receiving frames")
                    had_frame = True
                self._set_frame(frame)
            else:
                if self._is_stream_stale():
                    self.is_connected = False
                time.sleep(0.01)

        cap.release()
        self._cap = None
        return True

    def _run_gst_subprocess(self):
        if not shutil.which("gst-launch-1.0"):
            print("[RPi Camera]   gst-launch-1.0 not found; camera feed unavailable.")
            self.last_error = "gst-launch-1.0 not found"
            self.is_connected = False
            return

        self.backend = "gst-launch"

        # Decode RTP/H264 and stream concatenated JPEGs to stdout.
        cmd = [
            "gst-launch-1.0", "-q", "-e",
            "udpsrc", f"address={self.host}", f"port={self.port}",
            "caps=application/x-rtp,media=video,encoding-name=H264,payload=96,clock-rate=90000",
            "!", "rtpjitterbuffer", f"latency={self.latency_ms}", "drop-on-latency=true",
            "!", "rtph264depay",
            "!", "h264parse",
            "!", "decodebin",
            "!", "videoconvert",
        ]

        if self.flip_180:
            cmd += ["!", "videoflip", "method=rotate-180"]

        cmd += [
            "!", "videoscale",
            "!", f"video/x-raw,width={self.out_width},height={self.out_height}",
            "!", "queue", "max-size-buffers=1", "max-size-bytes=0", "max-size-time=0", "leaky=downstream",
            "!", "jpegenc", f"quality={self.jpeg_quality}",
            "!", "queue", "max-size-buffers=1", "max-size-bytes=0", "max-size-time=0", "leaky=downstream",
            "!", "fdsink", "fd=1", "sync=false", "async=false",
        ]

        print(f"[RPi Camera]   Listening on UDP port {self.port} …")
        self.is_listening = True
        self._gst_proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )

        self._stderr_thread = threading.Thread(target=self._drain_stderr, daemon=True)
        self._stderr_thread.start()

        stream = self._gst_proc.stdout
        if stream is None:
            self.is_connected = False
            return

        had_frame = False
        buffer = bytearray()
        while not self._stop_event.is_set():
            chunk = stream.read(8192)
            if not chunk:
                if self._gst_proc.poll() is not None:
                    if self._gst_proc.returncode not in (0, None):
                        self.last_error = f"gst-launch exited with code {self._gst_proc.returncode}"
                    break
                time.sleep(0.01)
                continue

            buffer.extend(chunk)

            while True:
                start = buffer.find(b"\xff\xd8")
                if start < 0:
                    if len(buffer) > 2:
                        del buffer[:-2]
                    break

                end = buffer.find(b"\xff\xd9", start + 2)
                if end < 0:
                    if start > 0:
                        del buffer[:start]
                    break

                jpg = bytes(buffer[start:end + 2])
                del buffer[:end + 2]

                if not had_frame:
                    print("[RPi Camera] ✓ Receiving frames")
                    had_frame = True
                # JPEG is already encoded by GStreamer; avoid re-decode/re-encode.
                self._set_jpeg_bytes(jpg)

            if self._is_stream_stale():
                self.is_connected = False

        self._cleanup_gst()

    def _is_stream_stale(self, timeout_s=2.0):
        return (time.monotonic() - self._last_frame_ts) > timeout_s

    def _drain_stderr(self):
        try:
            if self._gst_proc and self._gst_proc.stderr:
                for raw in self._gst_proc.stderr:
                    line = raw.decode(errors="ignore").strip()
                    if line and ("ERROR" in line.upper() or "not found" in line.lower()):
                        self.last_error = line
                    if self._stop_event.is_set():
                        break
        except Exception:
            pass

    def _cleanup_gst(self):
        proc = self._gst_proc
        self._gst_proc = None
        if not proc:
            return
        try:
            proc.terminate()
            proc.wait(timeout=1.5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    def _cleanup(self):
        self.is_connected = False
        self.is_listening = False
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None
        self._cleanup_gst()


def init_rpi_camera(
    host="0.0.0.0",
    port=6969,
    latency_ms=12,
    out_width=960,
    out_height=540,
    jpeg_quality=70,
    flip_180=False,
):
    receiver = RPiCameraReceiver(
        host=host,
        port=port,
        latency_ms=latency_ms,
        out_width=out_width,
        out_height=out_height,
        jpeg_quality=jpeg_quality,
        flip_180=flip_180,
    )
    receiver.start()
    return receiver


def generate_rpi_frames(rpi_camera):
    """Flask MJPEG generator for latest frame from the RPi camera receiver."""
    last_seq = -1
    while True:
        frame, seq = rpi_camera.wait_for_next_frame(last_seq, timeout=0.25)
        if frame is None:
            frame = rpi_camera.get_placeholder_jpeg()
        elif seq == last_seq:
            # no new frame yet
            continue

        last_seq = seq

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')