"""The adapter must satisfy Topside's interface exactly, or it is not drop-in.

Topside's own tests/test_camera.py defines a FakeArucoDetector with three
methods. That fake IS the interface contract -- if it compiles against
`_process_aruco_frame`, so must we.
"""

import cv2
import numpy as np

from gated_aruco.params import get_dictionary
from gated_aruco.topside_adapter import GatedArUcoMarkerDetector


def render(marker_id, side=240, pad=120, surround=255):
    """A marker on a white plate, big and clean enough to pass every gate."""
    d = get_dictionary()
    tile = d.generateImageMarker(marker_id, side, 1)
    img = cv2.copyMakeBorder(tile, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=surround)
    return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)


def test_interface_matches_topsides_fake_detector():
    d = GatedArUcoMarkerDetector()
    for name in ("detect_markers", "marker_detections", "draw_detected_markers"):
        assert callable(getattr(d, name)), name


def test_detect_markers_returns_the_opencv_triple():
    d = GatedArUcoMarkerDetector()
    out = d.detect_markers(np.zeros((480, 640, 3), np.uint8))
    assert isinstance(out, tuple) and len(out) == 3


def test_accepts_topsides_constructor_signature():
    """Topside constructs it bare and with camera_matrix/dist_coeffs."""
    GatedArUcoMarkerDetector()
    GatedArUcoMarkerDetector(
        camera_matrix=np.array([[900, 0, 640], [0, 900, 360], [0, 0, 1]], np.float32),
        dist_coeffs=np.zeros((5, 1), np.float32),
    )


def test_marker_detections_shape_is_unchanged():
    """ArucoPipelineLogger reads marker["id"] and marker["center"]."""
    d = GatedArUcoMarkerDetector()
    corners = (np.array([[[10, 10], [50, 10], [50, 50], [10, 50]]], np.float32),)
    ids = np.array([[61]], np.int32)
    got = d.marker_detections(corners, ids)
    assert got == [{"id": 61, "center": (30.0, 30.0)}]
    assert d.marker_detections(None, None) == []


def test_a_legal_marker_survives_and_is_confirmed():
    """Gating must not be so strict that a clean marker never reports."""
    d = GatedArUcoMarkerDetector(mission="visual", temporal_m=2, temporal_n=8)
    frame = render(61)
    seen = []
    for _ in range(4):
        corners, ids, _ = d.detect_markers(frame)
        seen.append([] if ids is None else ids.flatten().tolist())
    assert seen[0] == [], "confirmed on the first frame; temporal gate is not wired"
    assert 61 in seen[-1], f"a clean ID 61 never confirmed: {seen}"


def test_an_illegal_id_never_reaches_the_logger():
    """ID 0 is illegal in every mission and must not survive at any point."""
    d = GatedArUcoMarkerDetector(mission="visual")
    frame = render(0)
    for _ in range(12):
        _corners, ids, _ = d.detect_markers(frame)
        assert ids is None or 0 not in ids.flatten().tolist()
    assert any(k.startswith("allow_list") for k in d.stats), d.stats


def test_docking_mission_rejects_an_inspection_id():
    """Per-mission allow-lists must actually narrow, not default to 1-99."""
    d = GatedArUcoMarkerDetector(mission="docking")
    frame = render(61)  # legal on the structure, not docking
    for _ in range(8):
        _c, ids, _ = d.detect_markers(frame)
        assert ids is None or 61 not in ids.flatten().tolist()

    d2 = GatedArUcoMarkerDetector(mission="docking")
    frame2 = render(19)  # a real docking ID
    got = []
    for _ in range(6):
        _c, ids, _ = d2.detect_markers(frame2)
        got += [] if ids is None else ids.flatten().tolist()
    assert 19 in got


def test_enabled_false_is_a_transparent_passthrough():
    """An escape hatch that reverts to raw behaviour without a redeploy."""
    d = GatedArUcoMarkerDetector(mission="visual", enabled=False)
    frame = render(0)
    got = []
    for _ in range(3):
        _c, ids, _ = d.detect_markers(frame)
        got += [] if ids is None else ids.flatten().tolist()
    assert 0 in got, "disabled adapter should behave like the stock detector"


def test_reset_clears_temporal_state():
    d = GatedArUcoMarkerDetector(mission="visual", temporal_m=2)
    frame = render(61)
    for _ in range(4):
        d.detect_markers(frame)
    d.reset()
    _c, ids, _ = d.detect_markers(frame)
    assert ids is None, "temporal history survived reset()"


def test_draw_handles_empty_and_none():
    d = GatedArUcoMarkerDetector()
    f = np.zeros((100, 100, 3), np.uint8)
    assert d.draw_detected_markers(f, (), None) is f
