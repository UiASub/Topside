import threading
import time

import cv2

from lib.camera import DefaultCameraReceiver


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
