import threading
import time

import cv2
import numpy as np

from lib.aruco_logger import ArucoPipelineLogger
from lib.camera import DefaultCameraReceiver, IPCameraReceiver, _process_aruco_jpeg


class FakeClosedCapture:
    def isOpened(self):
        return False

    def release(self):
        pass


def test_default_camera_start_returns_before_device_opens(monkeypatch):
    opened = threading.Event()
    release = threading.Event()

    def fake_capture(device_index):
        opened.set()
        release.wait(timeout=1.0)
        return FakeClosedCapture()

    monkeypatch.setattr(cv2, "VideoCapture", fake_capture)

    camera = DefaultCameraReceiver(device_index=7)
    started_at = time.monotonic()
    camera.start()
    elapsed = time.monotonic() - started_at
    try:
        assert elapsed < 0.2
        assert camera.get_status()["device_index"] == 7
        assert opened.wait(timeout=1.0)
    finally:
        release.set()
        camera.stop()

    status = camera.get_status()
    assert status["connected"] is False
    assert status["listening"] is False


class FakeArucoDetector:
    def __init__(self):
        self.draw_calls = 0
        self.frame_shapes = []

    def detect_markers(self, frame):
        self.frame_shapes.append(frame.shape[:2])
        return [], None, []

    def marker_detections(self, corners, ids):
        return [
            {"id": 3, "center": (12, 10)},
            {"id": 2, "center": (8, 10)},
        ]

    def draw_detected_markers(self, frame, corners, ids):
        self.draw_calls += 1
        return frame


def test_ip_camera_frame_updates_aruco_logger_before_display_resize():
    logger = ArucoPipelineLogger()
    logger.start()
    camera = IPCameraReceiver("rtsp://example.invalid/stream", out_width=10, out_height=10, marker_logger=logger)
    detector = FakeArucoDetector()
    camera._detector = detector

    camera._set_frame(np.zeros((20, 20, 3), dtype=np.uint8))

    snapshot = logger.snapshot()
    assert [entry["id"] for entry in snapshot["entries"]] == [2, 3]
    assert snapshot["visible_ids"] == [2, 3]
    assert detector.frame_shapes == [(20, 20)]
    assert camera.get_latest_jpeg() is not None


def test_ip_camera_marker_overlay_can_be_disabled():
    logger = ArucoPipelineLogger()
    logger.set_marker_overlay_enabled(False)
    camera = IPCameraReceiver("rtsp://example.invalid/stream", marker_logger=logger)
    detector = FakeArucoDetector()
    camera._detector = detector

    camera._set_frame(np.zeros((20, 20, 3), dtype=np.uint8))

    assert detector.draw_calls == 0

    logger.set_marker_overlay_enabled(True)
    camera._set_frame(np.zeros((20, 20, 3), dtype=np.uint8))

    assert detector.draw_calls == 1


def test_aruco_jpeg_processing_updates_logger():
    logger = ArucoPipelineLogger()
    logger.start()
    detector = FakeArucoDetector()
    ok, buf = cv2.imencode(".jpg", np.zeros((20, 20, 3), dtype=np.uint8))
    assert ok

    jpg = _process_aruco_jpeg(buf.tobytes(), detector, logger, jpeg_quality=70)

    snapshot = logger.snapshot()
    assert [entry["id"] for entry in snapshot["entries"]] == [2, 3]
    assert detector.draw_calls == 1
    assert jpg.startswith(b"\xff\xd8")
