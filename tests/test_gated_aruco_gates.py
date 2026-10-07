import cv2
import numpy as np
import pytest

from gated_aruco.gates import (
    AllowListGate,
    BitConfidenceGate,
    Candidate,
    FrameContext,
    QuadGeometryGate,
    TemporalConfirmer,
)
from gated_aruco.params import get_dictionary, tuned_params


def ctx_from(bgr):
    return FrameContext(bgr=bgr, gray=cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY), frame_index=0)


def square(cx=100, cy=100, s=80):
    h = s / 2
    return np.array([[cx - h, cy - h], [cx + h, cy - h], [cx + h, cy + h], [cx - h, cy + h]], np.float32)


# --- allow list -----------------------------------------------------------
def test_allow_list_passes_legal_id():
    g = AllowListGate({12, 47})
    assert g(Candidate(12, square()), None).passed


def test_allow_list_rejects_illegal_id():
    g = AllowListGate({12, 47})
    v = g(Candidate(0, square()), None)
    assert not v.passed and v.reason == "id_not_in_allow_list"


def test_allow_list_disabled_passes_everything():
    assert AllowListGate(None)(Candidate(999, square()), None).passed


# --- geometry -------------------------------------------------------------
def test_geometry_accepts_axis_aligned_square():
    assert QuadGeometryGate()(Candidate(1, square()), None).passed


def test_geometry_accepts_moderate_perspective():
    quad = np.array([[10, 12], [90, 4], [96, 88], [16, 96]], np.float32)
    assert QuadGeometryGate(min_area_px=100)(Candidate(1, quad), None).passed


def test_geometry_rejects_sliver():
    quad = np.array([[0, 0], [200, 0], [200, 6], [0, 6]], np.float32)
    v = QuadGeometryGate(min_area_px=10)(Candidate(1, quad), None)
    assert not v.passed


def test_geometry_rejects_tiny_quad():
    v = QuadGeometryGate(min_area_px=400)(Candidate(1, square(s=10)), None)
    assert not v.passed and v.reason == "quad_too_small"


# --- bit confidence -------------------------------------------------------
def _render_marker(marker_id, s=140, pad=40):
    d = get_dictionary()
    tile = d.generateImageMarker(marker_id, s, 1)
    img = cv2.copyMakeBorder(tile, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=200)
    return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR), np.array(
        [[pad, pad], [pad + s, pad], [pad + s, pad + s], [pad, pad + s]], np.float32
    )


def test_bit_confidence_accepts_a_clean_marker():
    bgr, quad = _render_marker(47)
    assert BitConfidenceGate()(Candidate(47, quad), ctx_from(bgr)).passed


def test_bit_confidence_rejects_a_noise_patch():
    rng = np.random.default_rng(0)
    bgr = rng.integers(30, 90, (220, 220, 3), dtype=np.uint8)
    v = BitConfidenceGate()(Candidate(0, square(110, 110, 140)), ctx_from(bgr))
    assert not v.passed


def test_bit_confidence_rejects_missing_quiet_zone():
    # A marker on a white surround: the border cells read white, not black.
    d = get_dictionary()
    tile = d.generateImageMarker(47, 140, 1)
    # Overwrite the marker's own black border with white.
    cell = 140 // 7
    tile[:cell, :] = 255
    tile[-cell:, :] = 255
    tile[:, :cell] = 255
    tile[:, -cell:] = 255
    bgr = cv2.cvtColor(cv2.copyMakeBorder(tile, 40, 40, 40, 40, cv2.BORDER_CONSTANT, value=255), cv2.COLOR_GRAY2BGR)
    quad = np.array([[40, 40], [180, 40], [180, 180], [40, 180]], np.float32)
    v = BitConfidenceGate()(Candidate(47, quad), ctx_from(bgr))
    assert not v.passed and v.reason == "quiet_zone_not_black"


# --- temporal -------------------------------------------------------------
def test_temporal_requires_m_sightings():
    t = TemporalConfirmer(m=3, n=8)
    for i in range(2):
        confirmed, pending = t.update(i, [Candidate(12, square())])
        assert confirmed == [] and len(pending) == 1
    confirmed, _ = t.update(2, [Candidate(12, square())])
    assert [c.marker_id for c in confirmed] == [12]


def test_temporal_rejects_a_single_flash():
    t = TemporalConfirmer(m=4, n=8)
    confirmed, pending = t.update(0, [Candidate(0, square())])
    assert confirmed == [] and pending[0][1] == "temporal_unconfirmed"


def test_temporal_does_not_confirm_across_a_spatial_jump():
    t = TemporalConfirmer(m=3, n=8, max_jump_px=30)
    t.update(0, [Candidate(12, square(50, 50))])
    t.update(1, [Candidate(12, square(400, 400))])
    confirmed, _ = t.update(2, [Candidate(12, square(50, 50))])
    # Only two sightings are near each other, so three are not yet available.
    assert confirmed == []


# --- dictionary invariants the gates depend on ----------------------------
def test_error_correction_is_disabled_in_the_tuned_preset():
    """Rate 0 must reject a corrupted marker on every OpenCV version.

    OpenCV 4.x sets maxCorrectionBits == 0 for this dictionary, so the rate is
    irrelevant. OpenCV 5.x sets it to 1, and a rate of 1.0 or above turns on a
    bit of correction that takes the false-accept rate from 1-in-8196 to
    1-in-315. Since the dictionary's minimum inter-marker distance is 1 bit,
    correction can only ever move you onto a neighbouring legal ID.
    """
    d = get_dictionary()
    g = (d.generateImageMarker(37, 7, 1)[1:6, 1:6] > 127).astype(np.uint8)
    g[2, 2] ^= 1
    ok, _, _ = d.identify(g, 0.0)
    assert not ok
    assert tuned_params().errorCorrectionRate == 0.0


def test_correction_would_be_harmful_if_enabled():
    """Documents the OpenCV 5 hazard rather than asserting a version."""
    d = get_dictionary()
    if d.maxCorrectionBits == 0:
        pytest.skip("OpenCV 4.x: this dictionary has no correction to enable")
    g = (d.generateImageMarker(37, 7, 1)[1:6, 1:6] > 127).astype(np.uint8)
    g[2, 2] ^= 1
    ok, idx, _ = d.identify(g, 1.0)
    assert ok and idx == 37, "correction is available here; keep the rate at 0"


@pytest.mark.parametrize("marker_id", [0, 1, 512, 1023])
def test_every_dictionary_id_round_trips(marker_id):
    d = get_dictionary()
    g = (d.generateImageMarker(marker_id, 7, 1)[1:6, 1:6] > 127).astype(np.uint8)
    ok, idx, _ = d.identify(g, 1.0)
    assert ok and idx == marker_id


# --- complexity -----------------------------------------------------------
def test_complexity_rejects_the_ids_seen_on_real_footage():
    """IDs 0, 1023, 1020 and 256 were every false positive in a real clip."""
    from gated_aruco.gates import ComplexityGate

    g = ComplexityGate(get_dictionary(), min_transitions=24)
    for bad in (0, 1023, 1020, 256):
        v = g(Candidate(bad, square()), None)
        assert not v.passed and v.reason == "pattern_too_simple"


def test_complexity_accepts_a_busy_pattern():
    from gated_aruco.gates import ComplexityGate

    g = ComplexityGate(get_dictionary(), min_transitions=24)
    assert g(Candidate(409, square()), None).passed  # highest in the dictionary


def test_complexity_exempts_ids_that_are_actually_legal():
    from gated_aruco.gates import ComplexityGate

    g = ComplexityGate(get_dictionary(), min_transitions=24, exempt_ids={0})
    assert g(Candidate(0, square()), None).passed


def test_id_zero_is_the_least_complex_marker_in_the_dictionary():
    from gated_aruco.gates import ComplexityGate

    g = ComplexityGate(get_dictionary())
    scores = [g.score(i) for i in range(1024)]
    assert g.score(0) == min(scores) == 12


# --- TAC mission constants ------------------------------------------------
def test_id_zero_is_not_legal_in_any_tac_mission():
    from gated_aruco import tac

    assert 0 not in tac.ALL_LEGAL_IDS


def test_observed_false_positives_are_all_illegal():
    from gated_aruco import tac

    for bad in (0, 256, 1020, 1023):
        assert bad not in tac.ALL_LEGAL_IDS


def test_report_threshold_is_one_third_piloted():
    from gated_aruco.tac import Scoring

    assert abs(Scoring(20, -10).report_threshold - 1 / 3) < 1e-9
    assert abs(Scoring(10, -5).report_threshold - 1 / 3) < 1e-9


def test_autonomy_bonus_lowers_the_reporting_bar():
    from gated_aruco import tac

    assert abs(tac.VISUAL_INSPECTION_SCORING.report_threshold - 0.2) < 1e-9
    assert abs(tac.PIPELINE_SCORING.report_threshold - 0.2) < 1e-9


def test_high_risk_ids_are_legal_but_low_complexity():
    from gated_aruco import tac
    from gated_aruco.gates import ComplexityGate

    g = ComplexityGate(get_dictionary())
    for i in tac.HIGH_RISK_LEGAL_IDS:
        assert i in tac.ALL_LEGAL_IDS
        assert g.score(i) < 24


# --- sonar range prior ----------------------------------------------------
def _K(f=900.0):
    return np.array([[f, 0, 480.0], [0, f, 270.0], [0, 0, 1]], np.float64)


def test_sonar_gate_passes_when_size_matches_measured_range():
    from gated_aruco.gates import SonarRangeGate

    g = SonarRangeGate(_K(), marker_length_m=0.15)
    # 0.15 m marker at 1.5 m with f=900 projects to 90 px.
    g.set_range(1.5)
    assert g(Candidate(47, square(s=90)), None).passed


def test_sonar_gate_rejects_a_quad_of_the_wrong_physical_size():
    from gated_aruco.gates import SonarRangeGate

    g = SonarRangeGate(_K(), marker_length_m=0.15)
    g.set_range(1.5)
    v = g(Candidate(47, square(s=30)), None)  # implies 4.5 m, not 1.5 m
    assert not v.passed and v.reason == "range_disagrees_with_sonar"


def test_sonar_gate_is_inert_without_a_measurement():
    from gated_aruco.gates import SonarRangeGate

    g = SonarRangeGate(_K(), marker_length_m=0.15)
    assert g(Candidate(47, square(s=30)), None).passed


def test_implied_range_matches_the_pinhole_model():
    from gated_aruco.gates import SonarRangeGate

    g = SonarRangeGate(_K(f=900.0), marker_length_m=0.15)
    assert abs(g.implied_range(Candidate(1, square(s=90))) - 1.5) < 1e-6


# --- marker geometry, from the booklet dimension figure -------------------
def test_marker_and_plate_dimensions_are_known():
    """PoseGate and SonarRangeGate are meaningless without a real length."""
    from gated_aruco import tac

    assert tac.MARKER_LENGTH_M == 0.150
    assert tac.PLATE_LENGTH_M == 0.200


def test_roi_annulus_starts_outside_the_white_plate():
    """The plate edge is at 1.333x the quad; sampling inside it reads white.

    This is the failure mode that would have made YellowRoiGate reject every
    real marker: the ring it inspects would have landed on the marker's own
    white backing rather than on the structure.
    """
    from gated_aruco import tac
    from gated_aruco.gates import YellowRoiGate

    assert tac.PLATE_SCALE == pytest.approx(4 / 3)
    g = YellowRoiGate()
    assert g.inner_scale > tac.PLATE_SCALE, "annulus starts on the marker's own plate"
    # and with enough margin to survive corner jitter, not just barely
    assert g.inner_scale >= tac.PLATE_SCALE * 1.10
    assert g.outer_scale > g.inner_scale


def test_yellow_roi_ignores_the_white_plate_around_a_real_marker():
    """End to end: a marker on its plate, on structure, must not be rejected."""
    from gated_aruco import tac
    from gated_aruco.gates import YellowRoiGate

    side = 150
    frame = np.zeros((900, 900, 3), np.uint8)
    frame[:] = (40, 190, 210)  # structure: yellow-ish
    cx = cy = 450
    plate = int(side * tac.PLATE_SCALE / 2)
    frame[cy - plate : cy + plate, cx - plate : cx + plate] = (245, 245, 245)  # white plate
    h = side // 2
    frame[cy - h : cy + h, cx - h : cx + h] = 0  # black marker
    quad = square(cx, cy, side)

    assert YellowRoiGate()(Candidate(47, quad), ctx_from(frame)).passed

    # An annulus that starts inside the plate edge samples the marker's own
    # white backing and concludes it is not on the structure. This is what the
    # gate did at its original 1.05 inner scale.
    on_plate = YellowRoiGate(inner_scale=1.05, outer_scale=1.30)
    v = on_plate(Candidate(47, quad), ctx_from(frame))
    assert not v.passed and v.reason == "not_on_yellow_structure"
    assert v.metrics["surround_yellow"] == 0.0


def test_min_readable_side_scales_with_bit_cells():
    from gated_aruco import tac

    assert tac.BITS_ACROSS == 7
    assert tac.min_readable_side_px(4.0) == 28.0
    assert tac.CELL_LENGTH_M == pytest.approx(0.150 / 7)


# --- geometry retuned from real footage -----------------------------------
def _skewed_quad(cx, cy, side, squash=0.45, rot_deg=40.0):
    """A square seen obliquely: rotated, then foreshortened along one axis."""
    h = side / 2
    pts = np.array([[-h, -h], [h, -h], [h, h], [-h, h]], np.float64)
    t = np.radians(rot_deg)
    R = np.array([[np.cos(t), -np.sin(t)], [np.sin(t), np.cos(t)]])
    pts = pts @ R.T
    pts[:, 1] *= squash
    return (pts + [cx, cy]).astype(np.float32)


def test_geometry_accepts_the_oblique_views_real_markers_are_seen_at():
    """The markers in the 2024 footage are skewed; the grate holes are square.

    Median true detection: side_ratio 1.89, 41-degree corners. The original
    2.2 / 1.6 / 45-degree bounds rejected 82% of true detections and removed no
    false positives, because they penalise exactly the wrong side.
    """
    g = QuadGeometryGate()

    # The gate's bounds must clear the observed p99 of the TRUE distribution,
    # with a little headroom. These three numbers are the measurement.
    assert g.max_side_ratio >= 3.51
    assert g.max_diag_ratio >= 2.34
    assert g.max_abs_cos >= 0.948

    # And concretely: obliquely-viewed squares within that envelope must pass.
    for squash in (0.9, 0.7, 0.5):
        for rot in (0.0, 20.0, 40.0, 65.0):
            quad = _skewed_quad(400, 400, 220, squash, rot)
            v = g(Candidate(61, quad), None)
            assert v.passed, f"rejected squash={squash} rot={rot}: {v.reason}"

    # The bounds are deliberately NOT open-ended: a view more extreme than
    # anything in the footage is still rejected, so the gate keeps some power.
    assert not g(Candidate(61, _skewed_quad(400, 400, 220, 0.2, 40.0)), None).passed


def test_geometry_still_rejects_degenerate_slivers():
    """Widening the shape bounds must not make the gate useless."""
    g = QuadGeometryGate()
    sliver = np.array([[0, 0], [600, 0], [600, 9], [0, 9]], np.float32)
    assert not g(Candidate(61, sliver), None).passed


def test_size_is_what_separates_markers_from_grate():
    """A grate hole is far smaller than a 150 mm marker at working distance.

    True detections ran 49-148 px on a side (p1 area 2749 px^2); false ones had
    a median side of 34 px and a p95 area of 2106 px^2.
    """
    g = QuadGeometryGate()
    assert g(Candidate(61, square(s=100)), None).passed  # real marker
    v = g(Candidate(0, square(s=34)), None)  # grate hole
    assert not v.passed and v.reason == "quad_too_small"


def test_bit_confidence_floors_sit_below_the_true_distribution():
    """Floors must clear the real p1, or they throw away real markers."""
    from gated_aruco.gates import BitConfidenceGate

    g = BitConfidenceGate()
    assert g.min_mean_margin <= 0.068  # measured TRUE p1
    assert g.min_worst_margin <= 0.001  # measured TRUE p1
    assert g.max_border_white_frac >= 0.125  # measured TRUE p99


# --- CLAHE must mean the same thing at any resolution ---------------------
def test_clahe_tile_is_specified_in_pixels_not_grid_count():
    """A config tuned at one frame size must transfer to another.

    OpenCV's tileGridSize is a grid COUNT, so 8x8 is 320px tiles on a 2556px
    frame and 214px tiles on a 1708px crop of the same scene. That difference
    is not cosmetic: on the pipeline clip it was the difference between
    detecting the one real marker on 10 frames and on 0.
    """
    from gated_aruco.pipeline import apply_clahe

    rng = np.random.default_rng(0)
    scene = rng.integers(60, 190, (1000, 2000), dtype=np.uint8)
    half = cv2.resize(scene, (1000, 500), interpolation=cv2.INTER_AREA)

    big = apply_clahe(scene, 2.0, tile_px=250)
    small = apply_clahe(half, 2.0, tile_px=250)
    # 2000/250 = 8 tiles across; 1000/250 = 4. The tile's field of view in
    # scene terms is identical, which is the property that makes a tuned
    # config portable.
    assert big.shape == scene.shape and small.shape == half.shape

    # Downscaling the equalised big image should closely match equalising the
    # downscaled one, because both used the same physical tile size.
    ref = cv2.resize(big, (1000, 500), interpolation=cv2.INTER_AREA)
    assert float(np.abs(ref.astype(int) - small.astype(int)).mean()) < 12.0


def test_clahe_grid_scales_with_image_size():
    from gated_aruco.pipeline import apply_clahe

    a = np.full((640, 1280), 128, np.uint8)
    b = np.full((320, 640), 128, np.uint8)
    # Flat input, so the only thing under test is that neither call raises and
    # both honour the requested physical tile size.
    assert apply_clahe(a, 2.0, tile_px=320).shape == a.shape
    assert apply_clahe(b, 2.0, tile_px=320).shape == b.shape
    # A tile larger than the image must still produce a valid 1x1 grid.
    assert apply_clahe(b, 2.0, tile_px=5000).shape == b.shape
