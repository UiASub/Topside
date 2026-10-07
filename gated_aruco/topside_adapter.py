"""Drop-in replacement for Topside's `ArUcoMarkerDetector`.

Target: https://github.com/UiASub/Topside, `lib/camera.py`.

The seam is better than it looks. Topside's frame loop is:

    corners, ids, _rejected = detector.detect_markers(frame)
    detections = detector.marker_detections(corners, ids)
    marker_logger.record_visible(detections)
    frame = detector.draw_detected_markers(frame, corners, ids)

So `detect_markers` is the only place that decides what exists. If the gate
stack runs *inside* that call and returns only the survivors, then
`marker_detections`, `record_visible` and `draw_detected_markers` all keep
working unchanged and see only confirmed markers. No change to
`_process_aruco_frame`, none to `ArucoPipelineLogger`, none to the routes.

That also puts temporal confirmation where it has to be -- in front of the
logger rather than behind it. `ArucoPipelineLogger.record_visible` writes an
entry on an ID's FIRST sighting with no confirmation, so one bad frame puts a
false ID in the run log until someone calls `clear()`. Gating inside
`detect_markers` means the logger never hears about unconfirmed candidates.

Usage in lib/camera.py -- replace the three construction sites:

    from lib.aruco_gated import GatedArUcoMarkerDetector as ArUcoMarkerDetector

and set the mission and channel once, from config:

    ArUcoMarkerDetector(mission="visual", gray_mode="green", clahe=4.0)

What this does NOT fix, because it cannot from here:
  - `marker_detections()` still returns only {id, center}. Anything downstream
    that wants the gate metrics (confidence, margin, pose) needs that widened.
  - Pose gating stays off until the camera is calibrated. The 900/640/360
    intrinsics in `DefaultCameraReceiver` are placeholders, not a calibration.
"""

from __future__ import annotations

import cv2
import numpy as np

from . import tac
from .gates import (
    AllowListGate,
    BitConfidenceGate,
    Candidate,
    ComplexityGate,
    FrameContext,
    QuadGeometryGate,
    TemporalConfirmer,
    risk_tier_margins,
)
from .params import PRESETS, get_dictionary
from .pipeline import apply_clahe, to_gray


class GatedArUcoMarkerDetector:
    """Same interface as Topside's ArUcoMarkerDetector, with the gates applied.

    Interface contract, as exercised by Topside's own
    `tests/test_camera.py::FakeArucoDetector`:

        detect_markers(frame)                  -> (corners, ids, rejected)
        marker_detections(corners, ids)        -> [{"id", "center"}, ...]
        draw_detected_markers(frame, corners, ids) -> frame
    """

    def __init__(
        self,
        dictionary_name: str = "DICT_ARUCO_ORIGINAL",
        camera_matrix=None,
        dist_coeffs=None,
        mission: str = "visual",
        preset: str = "tuned",
        gray_mode: str = "bgr2gray",
        clahe: float = 0.0,
        temporal_m: int = 2,
        temporal_n: int = 8,
        risk_tiering: bool = True,
        enabled: bool = True,
    ):
        # Kept for signature compatibility. Topside passes these on one of its
        # three receivers and nothing has ever used them; PoseGate needs a real
        # calibration, not the placeholder 900/640/360.
        self.camera_matrix = camera_matrix
        self.dist_coeffs = dist_coeffs

        self.dictionary_name = dictionary_name
        self.mission = mission
        self.gray_mode = gray_mode
        self.clahe = clahe
        self.enabled = enabled

        self._dictionary = get_dictionary(dictionary_name)
        self._detector = cv2.aruco.ArucoDetector(self._dictionary, PRESETS[preset]())

        allowed = tac.MISSION_IDS.get(mission, tac.ALL_LEGAL_IDS)
        complexity = ComplexityGate(self._dictionary, exempt_ids=set(allowed))
        margins, extra = ({}, {})
        if risk_tiering:
            margins, extra = risk_tier_margins(self._dictionary, allowed, complexity)

        self.gates = [
            AllowListGate(set(allowed)),
            complexity,
            QuadGeometryGate(),
            BitConfidenceGate(tiers=margins),
        ]
        self.temporal = TemporalConfirmer(m=temporal_m, n=temporal_n, extra=extra)
        self._frame_index = -1
        self.stats: dict[str, int] = {}

    # -- Topside interface --------------------------------------------------
    def detect_markers(self, frame):
        """Detect, gate, confirm. Returns only markers that survived.

        The return shape matches `cv2.aruco.ArucoDetector.detectMarkers`:
        a tuple of (N,1,4,2) corner arrays, an (N,1) id array (or None), and
        the rejected candidates.
        """
        self._frame_index += 1
        gray = to_gray(frame, self.gray_mode)
        if self.clahe > 0:
            gray = apply_clahe(gray, self.clahe)

        corners, ids, rejected = self._detector.detectMarkers(gray)
        if not self.enabled or ids is None or len(ids) == 0:
            return corners, ids, rejected

        ctx = FrameContext(bgr=frame, gray=gray, frame_index=self._frame_index)
        survivors: list[tuple[Candidate, np.ndarray]] = []
        for marker_id, quad in zip(ids.flatten(), corners, strict=False):
            cand = Candidate(int(marker_id), np.asarray(quad, dtype=np.float32).reshape(4, 2))
            killed = None
            for gate in self.gates:
                verdict = gate(cand, ctx)
                if not verdict.passed:
                    killed = f"{gate.name}:{verdict.reason}"
                    break
            if killed is None:
                survivors.append((cand, quad))
            else:
                self.stats[killed] = self.stats.get(killed, 0) + 1

        confirmed, pending = self.temporal.update(self._frame_index, [c for c, _ in survivors])
        for _cand, reason in pending:
            self.stats[f"temporal:{reason}"] = self.stats.get(f"temporal:{reason}", 0) + 1

        keep = {id(c) for c in confirmed}
        out_corners = [q for c, q in survivors if id(c) in keep]
        if not out_corners:
            return (), None, rejected
        out_ids = np.array([[c.marker_id] for c in confirmed], dtype=np.int32)
        return tuple(out_corners), out_ids, rejected

    def marker_detections(self, corners, ids):
        if ids is None:
            return []
        detections = []
        for marker_id, marker_corners in zip(ids.flatten(), corners, strict=False):
            points = np.asarray(marker_corners, dtype=np.float32).reshape(-1, 2)
            center = points.mean(axis=0)
            detections.append({"id": int(marker_id), "center": (float(center[0]), float(center[1]))})
        return detections

    def draw_detected_markers(self, frame, corners, ids):
        if ids is not None and len(ids) > 0:
            cv2.aruco.drawDetectedMarkers(frame, corners, ids)
        return frame

    # -- extras, not part of Topside's interface ----------------------------
    def reset(self) -> None:
        self.temporal.reset()
        self.stats.clear()
        self._frame_index = -1
