import threading
import time

import cv2
import numpy as np

from lib.aruco_logger import ArucoPipelineLogger
from lib.camera import DefaultCameraReceiver, IPCameraReceiver


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
    def detect_markers(self, frame):
        return [], None, []

    def marker_detections(self, corners, ids):
        return [
            {"id": 3, "center": (300, 100)},
            {"id": 2, "center": (200, 100)},
        ]

    def draw_detected_markers(self, frame, corners, ids):
        return frame


def test_ip_camera_frame_updates_aruco_logger():
    logger = ArucoPipelineLogger()
    logger.start()
    camera = IPCameraReceiver("rtsp://example.invalid/stream", marker_logger=logger)
    camera._detector = FakeArucoDetector()

    camera._set_frame(np.zeros((20, 20, 3), dtype=np.uint8))

    snapshot = logger.snapshot()
    assert [entry["id"] for entry in snapshot["entries"]] == [2, 3]
    assert snapshot["visible_ids"] == [2, 3]
    assert camera.get_latest_jpeg() is not None
