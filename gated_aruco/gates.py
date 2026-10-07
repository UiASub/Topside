"""Rejection gates that run around the decoder, not inside it.

Each gate is a callable that takes a Candidate plus a FrameContext and returns
a Verdict. Gates are pure and independent so the harness can enable them one at
a time and attribute every kill to exactly one gate.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field

import cv2
import numpy as np


@dataclass
class Candidate:
    """One quad that the OpenCV decoder was willing to put an ID on."""

    marker_id: int
    corners: np.ndarray  # (4, 2) float32, OpenCV order
    metrics: dict[str, float] = field(default_factory=dict)

    @property
    def center(self) -> np.ndarray:
        return self.corners.mean(axis=0)


@dataclass
class FrameContext:
    """Everything a gate might need about the frame the candidate came from."""

    bgr: np.ndarray
    gray: np.ndarray
    frame_index: int


@dataclass
class Verdict:
    passed: bool
    reason: str = ""
    metrics: dict[str, float] = field(default_factory=dict)


PASS = Verdict(True)


# --------------------------------------------------------------------------
# 1. Allow-list
# --------------------------------------------------------------------------
class AllowListGate:
    """Reject any ID the competition did not place on the structure.

    Cheapest and highest-yield gate available. With DICT_ARUCO_ORIGINAL roughly
    1 in 8_196 random 5x5 patterns decodes; restricting to k legal IDs scales
    that by k/1024. Ten legal IDs makes it 1 in ~839_000.
    """

    name = "allow_list"

    def __init__(self, allowed_ids: set[int] | None):
        self.allowed = set(allowed_ids) if allowed_ids else None

    def __call__(self, cand: Candidate, ctx: FrameContext) -> Verdict:
        if self.allowed is None:
            return PASS
        if cand.marker_id in self.allowed:
            return PASS
        return Verdict(False, "id_not_in_allow_list", {"id": cand.marker_id})


# --------------------------------------------------------------------------
# 1b. Pattern complexity
# --------------------------------------------------------------------------
def bit_transitions(grid: np.ndarray) -> int:
    """Adjacent-tile colour changes, horizontally and vertically.

    The grid is padded with the black quiet zone first, so a marker whose
    payload runs to the edge is not credited with free transitions there.
    """
    p = np.pad(grid, 1, constant_values=0)
    return int((p[:, 1:] != p[:, :-1]).sum() + (p[1:, :] != p[:-1, :]).sum())


class ComplexityGate:
    """Reject IDs whose bit pattern is too simple to be evidence of anything.

    Derived from real footage, not theory. A 191 s DAG 1 transit clip with no
    structure in view produced 47 decodes, every one a false positive. The IDs:

        ID    0  transitions 12  rank    1 of 1024   (#....  one white column)
        ID 1023  transitions 16  rank    2 of 1024   (.###.  three columns)
        ID 1020  transitions 18  rank   11 of 1024
        ID  256  transitions 20  rank   27 of 1024

    All four are column stripes, and all four sit in the most degenerate 2.6%
    of the dictionary. Anything with vertical or horizontal banding -- a cable,
    a panel edge, a lighting gradient, a GUI border -- lands on one of these.
    Dictionary-wide the transition count runs 12 to 44 with a median of 30.

    Two ways to use this. If you can choose which IDs get printed, choose
    high-complexity ones (409 tops the list at 44) and this gate is free
    insurance. If the IDs are fixed and some are low-complexity, do not enable
    this gate for those IDs -- it would reject the real thing. Check first with
    tools/probe_dictionary.py.
    """

    name = "complexity"

    def __init__(self, dictionary, min_transitions: int = 24, exempt_ids: set[int] | None = None):
        self.min_transitions = min_transitions
        self.exempt = exempt_ids or set()
        n = dictionary.bytesList.shape[0]
        size = dictionary.markerSize
        self._score = {}
        for i in range(n):
            img = dictionary.generateImageMarker(i, size + 2, 1)
            self._score[i] = bit_transitions((img[1 : size + 1, 1 : size + 1] > 127).astype(np.uint8))

    def score(self, marker_id: int) -> int:
        return self._score.get(marker_id, 0)

    def __call__(self, cand: Candidate, ctx: FrameContext) -> Verdict:
        if cand.marker_id in self.exempt:
            return PASS
        t = self._score.get(cand.marker_id, 0)
        m = {"transitions": float(t)}
        cand.metrics.update(m)
        if t < self.min_transitions:
            return Verdict(False, "pattern_too_simple", m)
        return Verdict(True, "", m)


# --------------------------------------------------------------------------
# 2. Quad geometry
# --------------------------------------------------------------------------
class QuadGeometryGate:
    """Reject quads that are not plausibly a square seen through perspective.

    A grate hole viewed head-on passes this easily -- it *is* a square. The
    gate earns its place on skewed clutter, partially occluded holes and the
    long thin quads that adaptive thresholding produces along bar edges.

    MEASURED ON REAL FOOTAGE, and the result inverts the intuition. Across 497
    true and 272 false camera-region detections in the 2024 clips:

        metric        TRUE  p1 / p50 / p99      FALSE  p1 / p50 / p99
        side_ratio        1.46 / 1.89 / 3.51        1.08 / 3.82 / 8.45
        diag_ratio        1.14 / 1.95 / 2.34        1.00 / 1.11 / 2.86
        worst_cos         0.24 / 0.75 / 0.95        0.05 / 0.33 / 0.97
        area_px           2749 / 12200 / 24167       238 / 1537 / 4584

    The real markers are the SKEWED ones: they sit on a structure the ROV flies
    over at an angle, so a median true detection has 41-degree corners. The
    false positives are grate holes, which are genuinely square. So "is this a
    square" penalises the right answers and passes the wrong ones -- the
    original 2.2 / 1.6 / 45-degree bounds threw away 82% of true detections
    (205 -> 37) while removing no false positives at all.

    Size is what actually separates, and it separates almost perfectly: a
    150 mm marker at working distance is 50-148 px across, a grate hole is
    ~34 px. Prefer deriving min_area_px from tac.min_readable_side_px() and the
    expected range rather than inheriting the number below.

    The shape bounds are kept, widened to just outside the true distribution,
    because they still catch the degenerate slivers that thresholding produces
    along bar edges. They are no longer doing the main work.
    """

    name = "quad_geometry"

    def __init__(
        self,
        min_area_px: float = 2500.0,
        max_area_px: float = 400_000.0,
        max_side_ratio: float = 3.6,
        max_diag_ratio: float = 2.5,
        min_corner_angle_deg: float = 16.0,
    ):
        self.min_area_px = min_area_px
        self.max_area_px = max_area_px
        self.max_side_ratio = max_side_ratio
        self.max_diag_ratio = max_diag_ratio
        # A square's corners are 90 degrees, i.e. cos == 0. Perspective pushes
        # them away from 90 in both directions, so the admissible band is
        # symmetric: |cos| <= cos(min_corner_angle_deg).
        self.max_abs_cos = math.cos(math.radians(min_corner_angle_deg))

    def __call__(self, cand: Candidate, ctx: FrameContext) -> Verdict:
        c = cand.corners.astype(np.float64)
        area = abs(cv2.contourArea(c.astype(np.float32)))
        sides = np.linalg.norm(np.roll(c, -1, axis=0) - c, axis=1)
        if sides.min() <= 1e-6:
            return Verdict(False, "quad_degenerate")

        side_ratio = float(sides.max() / sides.min())
        d0 = float(np.linalg.norm(c[2] - c[0]))
        d1 = float(np.linalg.norm(c[3] - c[1]))
        diag_ratio = max(d0, d1) / max(min(d0, d1), 1e-6)

        m = {"area_px": area, "side_ratio": side_ratio, "diag_ratio": diag_ratio}

        if area < self.min_area_px:
            return Verdict(False, "quad_too_small", m)
        if area > self.max_area_px:
            return Verdict(False, "quad_too_large", m)
        if side_ratio > self.max_side_ratio:
            return Verdict(False, "quad_not_squarish", m)
        # A square under perspective keeps its diagonals close to equal until
        # the view angle gets extreme; wildly unequal diagonals mean the quad
        # was never a square.
        if diag_ratio > self.max_diag_ratio:
            return Verdict(False, "quad_diagonals_unequal", m)

        for i in range(4):
            a = c[i - 1] - c[i]
            b = c[(i + 1) % 4] - c[i]
            cosang = float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))
            if abs(cosang) > self.max_abs_cos:
                m["worst_cos"] = cosang
                return Verdict(False, "quad_corner_angle", m)

        cand.metrics.update(m)
        return Verdict(True, "", m)


# --------------------------------------------------------------------------
# 3. Bit confidence / decision margin
# --------------------------------------------------------------------------
class BitConfidenceGate:
    """Re-sample the bit grid and demand every cell vote decisively.

    OpenCV's decoder is a hard threshold: each cell is black or white with no
    notion of how close the call was. On a real marker most cells sit far from
    the threshold. On a noise patch that happens to land on a legal codeword,
    cells cluster near it. This gate recovers the confidence OpenCV discards.

    It also independently re-checks the quiet zone, because a marker taped to a
    yellow bar has a genuinely black border and a grate hole does not.

    Thresholds calibrated on a real DAG 1 frame (13/Jun/2024 13:17, -6.7 m,
    lights off), comparing the one true marker against three ID 0 false
    positives on grate and open water:

        metric              real (ID 61)   false (ID 0)
        mean_margin         0.132 - 0.200  0.007 - 0.062
        worst_margin        0.018 - 0.022  0.001 - 0.007
        border_white_frac   0.00           0.38 - 0.46

    border_white_frac is the standout: perfect separation with an enormous gap,
    because a real marker has a printed quiet zone and a patch of grate never
    does. mean_margin separates cleanly too. worst_margin barely separates and
    is kept only as a floor -- do not tighten it without re-measuring.

    Note how low the real values are. Thresholds tuned on clean synthetic
    footage (0.20 / 0.06) reject the real marker outright. A 6.7 m green-water
    marker genuinely does decode by a hair.

    Re-measured across 497 true and 272 false camera-region detections in the
    2024 clips, which moved the floors down again:

        metric              TRUE p1 / p50 / p99      FALSE p1 / p50 / p99
        mean_margin        0.068 / 0.183 / 0.369    0.016 / 0.099 / 0.191
        worst_margin       0.001 / 0.050 / 0.215    0.000 / 0.008 / 0.125
        border_white_frac  0.000 / 0.000 / 0.125    0.000 / 0.292 / 0.417

    border_white_frac remains the strongest signal by a wide margin and is the
    one to trust. mean_margin overlaps more than the single-frame measurement
    suggested, so its floor is set at the true p1 rather than anywhere near the
    false median. worst_margin barely separates at all -- it is a floor against
    degenerate patches, nothing more.
    """

    name = "bit_confidence"

    def __init__(
        self,
        marker_bits: int = 5,
        border_bits: int = 1,
        cell_px: int = 10,
        cell_margin: float = 0.3,
        min_mean_margin: float = 0.06,
        min_worst_margin: float = 0.0005,
        max_border_white_frac: float = 0.15,
        tiers: dict[int, float] | None = None,
    ):
        self.marker_bits = marker_bits
        self.border_bits = border_bits
        self.cell_px = cell_px
        self.cell_margin = cell_margin
        self.min_mean_margin = min_mean_margin
        self.min_worst_margin = min_worst_margin
        self.max_border_white_frac = max_border_white_frac
        # Per-ID margin multiplier. Some legal IDs are nearly as forgeable as
        # ID 0 and cannot be denied, so they are held to a higher standard
        # instead. See gates.risk_tier_margins().
        self.tiers = tiers or {}
        self.total_cells = marker_bits + 2 * border_bits

    def _warp(self, gray: np.ndarray, corners: np.ndarray) -> np.ndarray:
        n = self.total_cells * self.cell_px
        dst = np.array([[0, 0], [n - 1, 0], [n - 1, n - 1], [0, n - 1]], dtype=np.float32)
        h = cv2.getPerspectiveTransform(corners.astype(np.float32), dst)
        return cv2.warpPerspective(gray, h, (n, n), flags=cv2.INTER_LINEAR)

    def __call__(self, cand: Candidate, ctx: FrameContext) -> Verdict:
        patch = self._warp(ctx.gray, cand.corners)
        thresh, _ = cv2.threshold(patch, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)

        cp = self.cell_px
        inset = int(round(cp * self.cell_margin))
        lo, hi = inset, cp - inset
        if hi <= lo:
            lo, hi = 0, cp

        means = np.zeros((self.total_cells, self.total_cells), dtype=np.float32)
        for r in range(self.total_cells):
            for c in range(self.total_cells):
                cell = patch[r * cp + lo : r * cp + hi, c * cp + lo : c * cp + hi]
                means[r, c] = float(cell.mean())

        # Normalised distance of each cell from the decision threshold.
        margins = np.abs(means - thresh) / 255.0

        b = self.border_bits
        inner = margins[b:-b, b:-b]
        border_means = np.concatenate(
            [means[:b, :].ravel(), means[-b:, :].ravel(), means[b:-b, :b].ravel(), means[b:-b, -b:].ravel()]
        )
        border_white_frac = float((border_means > thresh).mean())

        m = {
            "mean_margin": float(inner.mean()),
            "worst_margin": float(inner.min()),
            "border_white_frac": border_white_frac,
            "otsu": float(thresh),
            "patch_std": float(patch.std()),
        }
        cand.metrics.update(m)

        mult = self.tiers.get(cand.marker_id, 1.0)
        if mult != 1.0:
            m["margin_multiplier"] = mult

        if border_white_frac > self.max_border_white_frac:
            return Verdict(False, "quiet_zone_not_black", m)
        if m["mean_margin"] < self.min_mean_margin * mult:
            return Verdict(False, "bit_margin_mean_low", m)
        if m["worst_margin"] < self.min_worst_margin * mult:
            return Verdict(False, "bit_margin_worst_low", m)
        return Verdict(True, "", m)


# --------------------------------------------------------------------------
# 4. Yellow ROI
# --------------------------------------------------------------------------
class YellowRoiGate:
    """Require the marker to sit on the yellow structure.

    Underwater the yellow drifts toward green as depth and turbidity change, so
    the hue window is deliberately wide and the test is on the *surround*, not
    the marker itself -- a marker is black and white, it is not yellow. We
    check an annulus just outside the quad.

    CALIBRATE THIS ON REAL FOOTAGE BEFORE TRUSTING IT. On the synthetic clip in
    this repo, structure paint that is OpenCV hue 22 in air measures hue 51 once
    red attenuation and the blue-green veil are applied. A window tuned in a
    dry lab will reject every real marker in the water. Run
    `tools/run_video.py --hue-report` on the actual clip and read the window off
    the histogram.
    """

    name = "yellow_roi"

    def __init__(
        self,
        hue_range: tuple[int, int] = (15, 62),
        min_sat: int = 60,
        min_val: int = 40,
        dilate_px: int = 9,
        min_surround_frac: float = 0.70,
        inner_scale: float = 1.50,
        outer_scale: float = 2.30,
    ):
        self.hue_range = hue_range
        self.min_sat = min_sat
        self.min_val = min_val
        self.dilate_px = dilate_px
        self.min_surround_frac = min_surround_frac
        # TAC markers sit on a white background inside a clear plastic frame,
        # so the ring immediately outside the quad is WHITE, not structure.
        # The annulus has to start beyond that plate or this gate rejects every
        # real marker.
        #
        # The booklet's dimension figure (pages 15 and 24) makes this exact: a
        # 150 mm marker on a 200 mm plate, so the plate edge sits at 200/150 =
        # 1.333x the detected quad. An inner_scale of 1.35 clears it by 1.2%,
        # which is inside subpixel corner-refinement jitter -- on the frames
        # where it lands short the gate reads the plate's own white as "not
        # structure" and throws away a real marker. 1.50 leaves 12% of margin.
        # See tac.PLATE_SCALE.
        self.inner_scale = inner_scale
        self.outer_scale = outer_scale

    def mask_for(self, bgr: np.ndarray) -> np.ndarray:
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        lo = np.array([self.hue_range[0], self.min_sat, self.min_val], np.uint8)
        hi = np.array([self.hue_range[1], 255, 255], np.uint8)
        mask = cv2.inRange(hsv, lo, hi)
        k = np.ones((self.dilate_px, self.dilate_px), np.uint8)
        return cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k)

    def __call__(self, cand: Candidate, ctx: FrameContext) -> Verdict:
        mask = getattr(ctx, "_yellow_mask", None)
        if mask is None:
            mask = self.mask_for(ctx.bgr)
            ctx._yellow_mask = mask  # cached per frame

        h, w = mask.shape
        c = cand.corners.astype(np.float32)
        centroid = c.mean(axis=0)

        outer = (centroid + (c - centroid) * self.outer_scale).astype(np.int32)
        inner = (centroid + (c - centroid) * self.inner_scale).astype(np.int32)

        ring = np.zeros((h, w), np.uint8)
        cv2.fillConvexPoly(ring, outer, 255)
        cv2.fillConvexPoly(ring, inner, 0)

        ring_px = int(ring.sum() // 255)
        if ring_px == 0:
            return Verdict(True, "", {"surround_yellow": -1.0})

        frac = float(cv2.bitwise_and(mask, ring).sum() // 255) / ring_px
        m = {"surround_yellow": frac}
        cand.metrics.update(m)
        if frac < self.min_surround_frac:
            return Verdict(False, "not_on_yellow_structure", m)
        return Verdict(True, "", m)


# --------------------------------------------------------------------------
# 5. Pose plausibility
# --------------------------------------------------------------------------
class PoseGate:
    """Solve for pose against the known physical marker size and sanity-check it.

    A grate hole is a different physical size from a marker. If it decodes, the
    pose solution puts it at an implausible range, or the reprojection error is
    high because the quad is not actually a rigid square.
    """

    name = "pose"

    def __init__(
        self,
        camera_matrix: np.ndarray,
        dist_coeffs: np.ndarray,
        marker_length_m: float,
        min_range_m: float = 0.15,
        max_range_m: float = 6.0,
        max_reproj_err_px: float = 2.5,
        max_tilt_deg: float = 75.0,
    ):
        self.K = np.asarray(camera_matrix, dtype=np.float64)
        self.D = np.asarray(dist_coeffs, dtype=np.float64)
        self.L = float(marker_length_m)
        self.min_range_m = min_range_m
        self.max_range_m = max_range_m
        self.max_reproj_err_px = max_reproj_err_px
        self.max_tilt_deg = max_tilt_deg
        h = self.L / 2.0
        self.obj = np.array([[-h, h, 0], [h, h, 0], [h, -h, 0], [-h, -h, 0]], dtype=np.float64)

    def __call__(self, cand: Candidate, ctx: FrameContext) -> Verdict:
        img_pts = cand.corners.astype(np.float64).reshape(4, 2)
        ok, rvec, tvec = cv2.solvePnP(self.obj, img_pts, self.K, self.D, flags=cv2.SOLVEPNP_IPPE_SQUARE)
        if not ok:
            return Verdict(False, "pose_unsolvable")

        proj, _ = cv2.projectPoints(self.obj, rvec, tvec, self.K, self.D)
        err = float(np.linalg.norm(proj.reshape(4, 2) - img_pts, axis=1).mean())
        rng = float(np.linalg.norm(tvec))

        R, _ = cv2.Rodrigues(rvec)
        # Angle between the marker normal and the camera view direction.
        tilt = math.degrees(math.acos(min(1.0, abs(float(R[2, 2])))))

        m = {"range_m": rng, "reproj_err_px": err, "tilt_deg": tilt}
        cand.metrics.update(m)

        if not (self.min_range_m <= rng <= self.max_range_m):
            return Verdict(False, "pose_range_implausible", m)
        if err > self.max_reproj_err_px:
            return Verdict(False, "pose_reproj_error", m)
        if tilt > self.max_tilt_deg:
            return Verdict(False, "pose_tilt_implausible", m)
        return Verdict(True, "", m)


# --------------------------------------------------------------------------
# 5b. Sonar range prior
# --------------------------------------------------------------------------
class SonarRangeGate:
    """Check the pose-implied range against a measured range to the structure.

    This is scalar fusion, deliberately. It needs one number per frame -- the
    range to whatever the vehicle is looking at -- and a rough boresight
    alignment between the sensor and the camera. It does NOT need sonar/camera
    extrinsic calibration, time-synchronised image-space registration, or any
    per-pixel correspondence, all of which are real projects on their own.

    Why it works. A marker of known physical side length subtends a predictable
    number of pixels at a given range. A false quad on the grate is a different
    physical size, so the range its pose solution implies will disagree with
    the measured range. PoseGate on its own can only ask "is this range
    somewhere in a plausible window"; with a measurement it can ask "does this
    range match the one we just observed", which is a far tighter question.

    Why not try to see the marker itself in the sonar. Three reasons, in order
    of how fatal they are:

    1. The printed pattern has no acoustic contrast. Ink does not change
       acoustic impedance, so sonar can never read an ID -- only find plates.
    2. Clear plastic on a metal structure is the wrong way round. Normal
       incidence intensity reflection against water is about 13% for acrylic or
       GRP versus 88% for steel, so the marker is acoustically *dimmer* than
       what it is mounted on, not brighter.
    3. Vertical aperture destroys image-space registration. An Oculus M750d
       integrates over 20 degrees of elevation, which at 1.5 m is a 0.53 m tall
       footprint. A return at a given range and bearing could be anywhere in
       that band, so it cannot be mapped to an image region.

    The range prior sidesteps all three. Any range source works: multibeam,
    a single-beam echosounder, a DVL altimeter, or the docking station's known
    geometry.

    Check the minimum range before choosing hardware. A Ping360 blanks below
    0.75 m because of transducer ringing, which is inside the distance at which
    a 5x5 marker is readable -- it goes blind exactly where this gate is
    needed. A DVL A50 works from 0.05 m.
    """

    name = "sonar_range"

    def __init__(
        self,
        camera_matrix: np.ndarray,
        marker_length_m: float,
        tolerance_frac: float = 0.25,
        min_tolerance_m: float = 0.10,
    ):
        self.K = np.asarray(camera_matrix, dtype=np.float64)
        self.L = float(marker_length_m)
        self.tolerance_frac = tolerance_frac
        self.min_tolerance_m = min_tolerance_m
        self._measured: float | None = None

    def set_range(self, range_m: float | None) -> None:
        """Feed the latest measured range. None disables the gate for that frame."""
        self._measured = range_m

    def implied_range(self, cand: Candidate) -> float:
        """Range a marker of the known size would have to be at to look this big.

        Uses the mean focal length and the mean projected side, which is exact
        for a fronto-parallel marker and degrades gracefully with tilt. That is
        fine here -- this gate is a coarse consistency check, not a pose solver.
        """
        c = cand.corners.astype(np.float64)
        sides = np.linalg.norm(np.roll(c, -1, axis=0) - c, axis=1)
        px = float(sides.mean())
        if px <= 1e-6:
            return float("inf")
        f = 0.5 * (self.K[0, 0] + self.K[1, 1])
        return f * self.L / px

    def __call__(self, cand: Candidate, ctx: FrameContext) -> Verdict:
        if self._measured is None:
            return PASS
        implied = self.implied_range(cand)
        tol = max(self.min_tolerance_m, self.tolerance_frac * self._measured)
        err = abs(implied - self._measured)
        m = {
            "implied_range_m": implied,
            "measured_range_m": float(self._measured),
            "range_err_m": err,
        }
        cand.metrics.update(m)
        if err > tol:
            return Verdict(False, "range_disagrees_with_sonar", m)
        return Verdict(True, "", m)


# --------------------------------------------------------------------------
# Risk tiering: per-ID sensitivity
# --------------------------------------------------------------------------
def risk_tier_margins(dictionary, legal_ids, complexity=None):
    """Per-ID (margin multiplier, extra confirmations), keyed by how forgeable
    the ID's own bit pattern is.

    The motivating case is ID 0 -- one white column, the least distinctive
    pattern in the dictionary, and the dominant false positive in the 2024
    footage. But ID 0 needs none of this: it is illegal in every TAC mission,
    so AllowListGate denies it outright, which is maximum strictness at zero
    recall cost. Per-ID sensitivity exists for the IDs you cannot deny.

    25 of the 99 legal IDs sit in the same degenerate tail -- 2, 3, 15 and 63
    have 18 transitions against ID 0's 12, out of a dictionary median of 30.
    If one of those is genuinely on the structure you must accept it, so the
    only lever left is to demand better evidence for it than for ID 73.

    Returns two dicts, ready to hand to BitConfidenceGate(tiers=...) and
    TemporalConfirmer(extra=...).
    """
    from . import tac

    if complexity is None:
        complexity = ComplexityGate(dictionary)
    margins: dict[int, float] = {}
    extra: dict[int, int] = {}
    for mid in legal_ids:
        tier = tac.risk_tier(mid, complexity.score(mid))
        mult, more = tac.TIER_MULTIPLIERS.get(tier, (1.0, 0))
        if mult != 1.0:
            margins[mid] = mult
        if more:
            extra[mid] = more
    return margins, extra


# --------------------------------------------------------------------------
# 6. Temporal M-of-N confirmation
# --------------------------------------------------------------------------
class TemporalConfirmer:
    """Only emit an ID after it appears in M of the last N frames near the same
    place.

    This is stateful and runs after the per-frame gates, not as one of them.
    It is the last line of defence and the one that matters most operationally:
    the existing ArucoPipelineLogger never forgets an ID, so a single bad frame
    permanently corrupts the run log. Confirmation has to happen before the
    logger sees anything.
    """

    name = "temporal"

    def __init__(self, m: int = 2, n: int = 8, max_jump_px: float = 60.0, extra: dict[int, int] | None = None):
        self.m = m
        self.n = n
        self.max_jump_px = max_jump_px
        # Per-ID extra confirmations, for legal-but-forgeable IDs.
        self.extra = extra or {}
        self._history: dict[int, deque[tuple[int, np.ndarray]]] = {}

    def update(
        self, frame_index: int, survivors: list[Candidate]
    ) -> tuple[list[Candidate], list[tuple[Candidate, str]]]:
        confirmed: list[Candidate] = []
        pending: list[tuple[Candidate, str]] = []

        for cand in survivors:
            hist = self._history.setdefault(cand.marker_id, deque(maxlen=self.n * 4))
            hist.append((frame_index, cand.center.copy()))

            window = [(fi, ctr) for fi, ctr in hist if frame_index - fi < self.n]
            near = [ctr for _, ctr in window if np.linalg.norm(ctr - cand.center) <= self.max_jump_px]
            hits = len(near)
            cand.metrics["temporal_hits"] = float(hits)
            need = self.m + self.extra.get(cand.marker_id, 0)
            cand.metrics["temporal_needed"] = float(need)

            if hits >= need:
                confirmed.append(cand)
            else:
                pending.append((cand, "temporal_unconfirmed"))

        return confirmed, pending

    def reset(self) -> None:
        self._history.clear()
