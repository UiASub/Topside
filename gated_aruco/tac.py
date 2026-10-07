"""TAC Challenge mission constants. Every value here is a rules quote.

Sources, and they now agree:
  - Mission Booklet 2026, last reviewed March 2026.
    https://tacchallenge.com/wp-content/uploads/2026/03/Mission-Booklet-2026.pdf
  - Mission Booklet 2024, Revision 1 -- the rules in force when the footage in
    this repo was shot.

The 2026 booklet asserts the missions are unchanged from 2024; that was taken
on trust here until the 2024 booklet was read directly. It checks out. ID
ranges, repeat rules, per-marker scoring, the 150 mm marker on a 200 mm plate,
RAL 1004 for the structure and the 200 mm yellow pipe are identical in both.

Re-read the booklet before the competition anyway: rules move, and the parts
that moved last time would not have announced themselves.
"""

from __future__ import annotations

from dataclasses import dataclass

# --------------------------------------------------------------------------
# Legal ID sets
# --------------------------------------------------------------------------
# Visual Inspection (the yellow structure): 5-10 markers, IDs 1-99, a given ID
# MAY occur more than once, positions and rotations arbitrary.
VISUAL_INSPECTION_IDS = frozenset(range(1, 100))

# Pipeline Inspection: 4-10 markers, IDs 1-99, a given ID will NOT repeat,
# markers horizontal and at least 0.2 m apart.
PIPELINE_IDS = frozenset(range(1, 100))

# Subsea Docking: exactly four markers at known positions and known IDs.
DOCKING_IDS = frozenset({7, 19, 28, 96})

ALL_LEGAL_IDS = VISUAL_INSPECTION_IDS | PIPELINE_IDS | DOCKING_IDS

# Use the allow-list for the mission you are actually flying, not the union.
# The allow-list is the cheapest gate in the stack and its strength scales with
# how few IDs you accept -- 1 in 8,196 arbitrary quads decode at all, and
# restricting to k of the 1024 IDs scales that by 1024/k:
#
#     allow-list             k     1 arbitrary quad in
#     none                1024                   8,196
#     1-99 (inspection)     99                  84,775
#     {7,19,28,96}           4               2,097,152
#
# Flying the docking mission with a 1-99 allow-list throws away a 25x
# improvement for nothing.
MISSION_IDS = {
    "visual": VISUAL_INSPECTION_IDS,
    "pipeline": PIPELINE_IDS,
    "docking": DOCKING_IDS,
}

# ID 0 is not legal in any mission. It is also the single most forgeable
# pattern in the dictionary (one white column, 12 transitions, rank 1 of 1024)
# and was the dominant false positive in the 2024 footage. Denying it is free.

# --------------------------------------------------------------------------
# Structure and marker appearance
# --------------------------------------------------------------------------
STRUCTURE_RAL = "RAL 1004 golden yellow"
STRUCTURE_RGB = (228, 158, 0)
PIPELINE_RGB = STRUCTURE_RGB  # booklet says pipeline colour is yellow
PIPELINE_DIAMETER_M = 0.200
PIPELINE_MAX_LENGTH_M = 10.0
PIPELINE_MIN_MARKER_SPACING_M = 0.200  # markers at least 0.2 m apart

# Visual Inspection structure, overall dimensions from the 2024 booklet.
# Useful because PoseGate's range window and QuadGeometryGate's size bounds
# should come from geometry, not from a fitted pixel distribution: you cannot
# be further from a marker than you can be and still have the structure in
# frame, and you cannot be closer than the vehicle can physically get.
STRUCTURE_WIDTH_M = 2.485
STRUCTURE_HEIGHT_M = 1.593
STRUCTURE_DEPTH_M = 1.280

# Subsea Docking station. Note the docking plate is WHITE, not yellow -- a
# colour ROI gate tuned on the yellow structure is not merely miscalibrated
# here, it is inverted. One more reason to keep colour gating optional.
DOCKING_PLATE_SIZE_M = (1.200, 0.800)  # EUR-pallet footprint
DOCKING_PLATE_COLOUR = "white"
DOCKING_MARKER_SIZE_M = 0.150  # per the page 9 dimension figure
DOCKING_MARKER_INSET_M = 0.035  # from the plate edge

# CAUTION: the docking figure dimensions the whole tag assembly at 150 mm and
# the docking section, unlike the pipeline and structure sections, does not say
# "white background". So for docking the 150 mm may span marker PLUS frame,
# making the black marker smaller than 150 mm. MARKER_LENGTH_M below is the
# inspection-mission value and is documented in both booklets; measure a
# docking tag before trusting pose on that mission.
DOCKING_MARKER_DIMENSION_IS_AMBIGUOUS = True
VALVE_RAL = "RAL 2004 pure orange"
VALVE_RGB = (226, 83, 3)

# "The frame around the marker is made of clear plastic with a white
# background." So the ring immediately outside a marker is WHITE, not yellow.
# A yellow-ROI gate must sample far enough out to clear that white border, or
# it will reject every real marker.
MARKER_HAS_WHITE_SURROUND = True

# Read off the dimension figures on booklet pages 15 (pipeline) and 24
# (structure). Both missions use the same plate, and the two figures agree.
#
#     +-----------------------------+  <- 200 mm white plate, clear frame
#     |   +---------------------+   |
#     |   |                     |   |  <- 150 mm black marker, INCLUDING its
#     |   |     black border    |   |     printed black quiet-zone ring
#     |   |     + 5x5 payload   |   |
#     |   +---------------------+   |
#     +-----------------------------+
#
# OpenCV returns the corners of the outer edge of the black border, so the
# quad it hands back is the 150 mm square. That is the length PoseGate and
# SonarRangeGate need.
MARKER_LENGTH_M: float = 0.150

# The white plate around it, as a multiple of the detected quad.
PLATE_LENGTH_M: float = 0.200
PLATE_SCALE: float = PLATE_LENGTH_M / MARKER_LENGTH_M  # 1.3333...

# Consequence for YellowRoiGate. The gate samples an annulus outside the quad
# and asks whether it looks like structure. The white plate reaches exactly
# PLATE_SCALE, so an annulus starting at 1.35 clears it by 1.2% -- inside the
# jitter of subpixel corner refinement, and inside the tolerance of a plate cut
# by hand. Any frame where it lands short reads the plate's own white as
# "not structure" and rejects a real marker. Start beyond it with real margin.
ROI_INNER_SCALE: float = 1.50
ROI_OUTER_SCALE: float = 2.30

# Bit cell geometry, for the "is this marker even resolvable" question.
# DICT_ARUCO_ORIGINAL is 5x5 payload plus a 1-cell border = 7 cells across the
# 150 mm marker, so one cell is 150/7 = 21.4 mm.
BITS_ACROSS = 7
CELL_LENGTH_M: float = MARKER_LENGTH_M / BITS_ACROSS


def plausible_range_m(sensor_width_px: int, focal_px: float, min_px_per_cell: float = 4.0) -> tuple[float, float]:
    """(near, far) working range over which a marker is both visible and readable.

    Far limit: the range at which the marker shrinks below min_px_per_cell and
    its 25 payload bits stop being decodable.
    Near limit: the range at which the 200 mm plate fills the frame width, i.e.
    you can no longer see the whole marker.

    Derive PoseGate's window from this rather than guessing it.
    """
    far = focal_px * MARKER_LENGTH_M / (min_px_per_cell * BITS_ACROSS)
    near = focal_px * PLATE_LENGTH_M / sensor_width_px
    return near, far


def min_readable_side_px(px_per_cell: float = 4.0) -> float:
    """Quad side, in pixels, below which the 25 payload bits are not readable.

    Four pixels per cell is the usual floor for a hard-threshold sampler: below
    it, blur from neighbouring cells decides the vote. Use it to set
    QuadGeometryGate's min_area_px rather than guessing.
    """
    return px_per_cell * BITS_ACROSS


# --------------------------------------------------------------------------
# Scoring, and what it implies about the precision/recall trade
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Scoring:
    correct: int
    incorrect: int
    autonomous_bonus: int = 0

    @property
    def report_threshold(self) -> float:
        """Minimum confidence at which reporting an ID has positive expected value.

        EV = p * (correct + bonus) - (1 - p) * |incorrect|, so report when
        p > |incorrect| / (correct + bonus + |incorrect|).
        """
        gain = self.correct + self.autonomous_bonus
        loss = abs(self.incorrect)
        return loss / (gain + loss)


VISUAL_INSPECTION_SCORING = Scoring(correct=20, incorrect=-10, autonomous_bonus=20)
PIPELINE_SCORING = Scoring(correct=10, incorrect=-5, autonomous_bonus=10)

# --------------------------------------------------------------------------
# Pipeline only: the deliverable is an ORDERED list, worth 50 more points
# --------------------------------------------------------------------------
# This is not in the Visual Inspection mission and it is easy to miss, because
# it changes the deliverable rather than the score per marker.
PIPELINE_ORDER_BONUS = 25  # all reported markers in the correct order
PIPELINE_START_BONUS = 25  # sequence starts from the pinger end
PIPELINE_ORDER_MIN_IDS = 3  # order bonus needs more than two IDs
PIPELINE_START_MIN_IDS = 2  # start bonus needs more than one ID

# The pinger (MFP-1, 30 kHz, 2 s repetition, 4 ms pulse) sits at one end of the
# pipeline and DEFINES which end is the start. A mirrored sequence also scores.
#
# Two properties of this scoring matter for the detector, and both are
# reassuring -- worked through against the booklet's own examples:
#
#   A false positive does NOT break the order bonus. Booklet example
#   "56,5,20,32" against a truth of 56,77,5,80,32 scores +30 for three correct,
#   -5 for the incorrect 20, and still collects BOTH +25 bonuses. The wrong ID
#   sat between two correct ones and the order was still judged correct.
#
#   A missed marker does not break it either: "Any markers missing from the
#   list will not affect this score."
#
# So the sequence bonuses are robust in both directions and do not change the
# per-marker expected-value threshold below. What they do change is the
# deliverable: the pipeline pipeline must preserve ORDER OF FIRST SIGHTING,
# not just the set of IDs. A detector that reports a set throws away 50 points.
PIPELINE_DELIVERABLE_IS_ORDERED = True

# Both missions: report at p > 1/3 piloted, p > 1/5 with the autonomy bonus.
# The mission score also cannot go below zero, so once you hold a few
# confident IDs the downside on a marginal one is capped.
#
# This is the opposite of the instinct the false-positive problem creates. The
# goal is not zero false positives -- it is a calibrated confidence thresholded
# at the point above. A gate stack tuned to never be wrong will silently drop
# real markers worth 40 points each to avoid 10-point mistakes.


# --------------------------------------------------------------------------
# Risk tiering
# --------------------------------------------------------------------------
# 25 of the 99 legal IDs sit in the low-complexity tail of the dictionary and
# cannot be denied, because they are legitimate answers. Treat them as
# high-risk instead: require a larger bit-decision margin and more temporal
# confirmations before reporting them.
HIGH_RISK_LEGAL_IDS = frozenset(
    {
        2,
        3,
        15,
        63,  # 18 transitions
        1,
        4,
        8,
        10,
        12,
        16,
        32,
        48,
        60,
        64,  # 20
        5,
        7,
        11,
        14,
        20,
        31,
        40,
        42,
        47,
        62,
        80,  # 22
    }
)

# Highest-complexity legal IDs, for reference if the team ever gets to choose:
SAFEST_LEGAL_IDS = (73, 89, 97, 25, 70, 77, 98, 99)


def risk_tier(marker_id: int, transitions: int) -> str:
    """Coarse risk label for an ID, used to scale confirmation strictness."""
    if marker_id not in ALL_LEGAL_IDS:
        return "illegal"
    if transitions <= 20:
        return "high"
    if transitions <= 24:
        return "medium"
    return "low"


TIER_MULTIPLIERS = {
    # tier: (bit-margin multiplier, extra temporal confirmations)
    "high": (1.6, 3),
    "medium": (1.25, 1),
    "low": (1.0, 0),
}
