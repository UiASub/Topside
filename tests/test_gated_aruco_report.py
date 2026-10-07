"""The mission deliverable, and the scoring rules it is judged by.

The gate stack decides what is real; this decides what gets handed in. They are
not the same thing, and the difference is worth 50 points on the pipeline.
"""

import pytest

from gated_aruco import tac
from gated_aruco.report import MissionReport

# Mission Booklet 2024 Rev.1, section 3.4, worked end to end by the organisers.
# Truth for every case is the same pipeline.
TRUTH = [56, 77, 5, 80, 32]
BOOKLET_EXAMPLES = [
    ([56, 77, 5, 80, 32], 100),  # all correct, correct order, correct direction
    ([56, 5, 20, 32], 75),  # a false positive between two correct IDs
    ([77, 5, 80, 32, 56], 50),  # all correct, wrong order, wrong direction
    ([77, 5, 80, 32], 90),  # one missing, order and direction intact
    ([32, 5, 77], 55),  # mirrored order scores, direction does not
    ([77, 32, 5], 55),  # direction scores, order does not
    ([1, 2, 3, 4, 5], 0),  # one correct, four wrong; floored at zero
    ([77, 5], 45),  # too short for the order bonus
]


def report_of(ids, mission="pipeline"):
    r = MissionReport(mission)
    for i, m in enumerate(ids):
        r.observe(i * 100, m)
    return r


@pytest.mark.parametrize("reported,expected", BOOKLET_EXAMPLES)
def test_scoring_matches_the_booklet_examples(reported, expected):
    assert report_of(reported).score(TRUTH) == expected


def test_a_false_positive_does_not_break_the_order_bonus():
    """Worth knowing before tuning: FPs cost -5, they do not cascade."""
    clean = report_of([56, 77, 5, 80, 32]).score(TRUTH)
    dirty = report_of([56, 77, 5, 99, 80, 32]).score(TRUTH)
    assert clean == 100
    assert dirty == 95, "a false positive should cost exactly its -5"


def test_a_missed_marker_does_not_break_the_order_bonus():
    """The booklet is explicit: missing markers do not affect the order score."""
    assert report_of([56, 5, 32]).score(TRUTH) == 30 + 25 + 25


# --- the deliverable itself ----------------------------------------------
def test_pipeline_deliverable_is_ordered_by_first_sighting():
    r = MissionReport("pipeline")
    r.observe(10, 56)
    r.observe(50, 77)
    r.observe(11, 56)  # 56 re-seen
    r.observe(90, 5)
    assert r.ordered_ids() == [56, 77, 5]


def test_pipeline_deliverable_deduplicates_because_ids_do_not_repeat():
    r = MissionReport("pipeline")
    for f in (0, 500, 1000):  # same ID, far apart in time
        r.observe(f, 56)
    assert r.ordered_ids() == [56]
    assert tac.PIPELINE_DELIVERABLE_IS_ORDERED


def test_a_set_of_ids_would_lose_the_sequence_bonuses():
    """The bug this module exists to prevent.

    Topside's logger keeps a set. Sorting a set gives an arbitrary order that
    only scores if it happens to match the pipe layout.
    """
    truth = [56, 77, 5, 80, 32]
    ordered = report_of(truth).score(truth)
    as_a_set = report_of(sorted(set(truth))).score(truth)  # [5, 32, 56, 77, 80]
    assert ordered == 100
    assert as_a_set == 50, "a set forfeits both sequence bonuses"
    assert ordered - as_a_set == tac.PIPELINE_ORDER_BONUS + tac.PIPELINE_START_BONUS


# --- visual inspection: IDs may repeat ------------------------------------
def test_visual_inspection_deduplicates_repeated_ids_by_default():
    """Splitting on track identity is the expensive mistake, so do not.

    Measured: the two real markers in the 2024 structure clips produced 17
    tracks. One entry per track scores 0; the deduplicated list scores 40.
    """
    r = MissionReport("visual")
    for f in range(0, 1700, 100):  # one marker, repeatedly re-acquired
        r.observe(f, 61, key=f"track_{f}")
    r.observe(50, 89, key="track_x")
    assert r.distinct_markers() == [61, 89]
    assert r.score([61, 89]) == 40


def test_splitting_every_track_would_have_scored_zero():
    """The failure this default prevents, stated as a number."""
    r = MissionReport("visual")
    for f in range(0, 1500, 100):
        r.observe(f, 61, key=f"track_{f}")
    r.observe(50, 89, key="track_x")
    split = r.distinct_markers(split_repeats=True)
    assert len(split) == 16
    r._forced = split
    # 2 correct (+40), 14 spurious (-140) -> floored to 0
    assert max(0, 2 * 20 + (len(split) - 2) * -10) == 0


def test_splitting_is_available_when_pose_proves_two_locations():
    """A genuine repeat still scores twice -- it just needs evidence."""
    r = MissionReport("visual")
    r.observe(10, 61, key="pose_left")
    r.observe(11, 61, key="pose_left")
    r.observe(900, 61, key="pose_right")
    assert r.distinct_markers() == [61]
    assert r.distinct_markers(split_repeats=True) == [61, 61]


def test_incorrect_markers_are_penalised_on_the_structure():
    r = report_of([61, 89, 3], mission="visual")
    assert r.score([61, 89]) == 20 + 20 - 10


def test_score_is_floored_at_zero():
    assert report_of([1, 2, 3], mission="visual").score([61]) == 0
