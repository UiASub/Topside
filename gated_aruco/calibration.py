"""Every threshold that came from looking at footage, in one place.

There are two kinds of number in this repo and conflating them is how a gate
stack quietly stops working when the camera changes.

**Rules numbers** are facts about the competition: the legal ID range, the
dictionary, the 150 mm marker on its 200 mm plate. They live in `tac.py`, they
came out of the Mission Booklet, and they only change when the booklet does.

**Calibration numbers** are the ones below. They came from measuring specific
footage, and every one of them is only as good as the footage it came from. The
2024 archive clips are recordings of the *pilot station*, so their camera panels
are rescaled and compressed twice: measured against natively-rendered GUI text
in the same frame, the camera panel reaches only about half the spatial
frequency its pixel dimensions imply. That has a predictable direction:

    thresholds derived here are CONSERVATIVE for a raw camera feed.

A raw feed is sharper, so real markers will decode with *larger* bit margins
than the ones seen here, and the margin floors below will pass them
comfortably. The risk runs the other way: a sharper feed also resolves more
structure detail, so the false-positive rate must be re-measured, not assumed
to improve.

Each field carries a PROVENANCE entry saying where it came from and whether it
survives a change of footage. `needs_retune()` prints the shortlist.
"""

from __future__ import annotations

from dataclasses import dataclass, fields


@dataclass(frozen=True)
class Calibration:
    """A threshold set, tied to the footage it was measured on."""

    name: str
    source: str

    # -- BitConfidenceGate --------------------------------------------------
    min_mean_margin: float = 0.06
    min_worst_margin: float = 0.0005
    max_border_white_frac: float = 0.15

    # -- QuadGeometryGate ---------------------------------------------------
    min_area_px: float = 2500.0
    max_side_ratio: float = 3.6
    max_diag_ratio: float = 2.5
    min_corner_angle_deg: float = 16.0

    # -- ComplexityGate -----------------------------------------------------
    min_transitions: int = 24

    # -- Structure ROI ------------------------------------------------------
    # On real DAG 1 footage the structure reads GREEN, not yellow: at 6.7 m
    # with no artificial light the red channel is essentially gone. Hue is
    # therefore useless and the blue/green ratio is used instead.
    max_bg_ratio: float = 0.62
    min_green: int = 60
    min_surround_frac: float = 0.70

    # -- TemporalConfirmer --------------------------------------------------
    temporal_m: int = 2
    temporal_n: int = 8
    max_jump_px: float = 60.0

    # -- Detector front end -------------------------------------------------
    min_otsu_std_dev: float = 12.0
    use_clahe: bool = True
    gray_mode: str = "bgr2gray"


# What each number rests on, and whether it survives new footage.
#   "rules"    - from the Mission Booklet, footage-independent
#   "physics"  - follows from optics or the dictionary, footage-independent
#   "footage"  - measured on the 2024 screen recordings, MUST be re-derived
PROVENANCE: dict[str, tuple[str, str]] = {
    "min_mean_margin": (
        "footage",
        "Separates a real marker from a grate patch, but the gap is the thing "
        "that transfers, not the value. Screen-recorded markers decode by a "
        "hair; a raw feed should show markedly larger margins. Re-derive from "
        "the labelled-track histogram and keep the same fraction of headroom.",
    ),
    "min_worst_margin": (
        "footage",
        "Barely separated even on the frame it was tuned on. Kept as a floor "
        "only. Do not tighten without re-measuring.",
    ),
    "max_border_white_frac": (
        "physics",
        "A real marker has a printed black quiet zone and a grate hole does "
        "not. Perfect separation with a large gap on real footage. This is the "
        "most robust gate in the stack and should survive any camera.",
    ),
    "min_area_px": (
        "footage",
        "Depends on sensor resolution and working distance. Prefer deriving it "
        "from tac.min_readable_side_px() and the actual frame size rather than "
        "carrying this number across.",
    ),
    "max_side_ratio": ("physics", "Perspective bound on a square. Camera-independent."),
    "max_diag_ratio": ("physics", "Perspective bound on a square. Camera-independent."),
    "min_corner_angle_deg": ("physics", "Perspective bound on a square. Camera-independent."),
    "min_transitions": (
        "rules",
        "A property of the dictionary, not the camera. But note 25 of the 99 "
        "legal IDs fall below 24 transitions, so this gate must exempt them "
        "(tac.HIGH_RISK_LEGAL_IDS) or it rejects legitimate markers.",
    ),
    "max_bg_ratio": (
        "footage",
        "Water colour, depth and lighting all move this. Measured at -6.7 m "
        "with lights OFF. With lights on, red returns and the structure reads "
        "yellow again, which would invert the test. Re-derive per dive.",
    ),
    "min_green": ("footage", "Exposure dependent. Re-derive with max_bg_ratio."),
    "min_surround_frac": (
        "footage",
        "How much of the annulus must look like structure. Depends on how cluttered the mounting is.",
    ),
    "temporal_m": (
        "footage",
        "Trades latency for confidence and depends on frame rate and how fast "
        "the vehicle moves. At 13.5 fps here, 4-of-8 costs about 0.3 s.",
    ),
    "temporal_n": ("footage", "See temporal_m."),
    "max_jump_px": (
        "footage",
        "Pixels a marker may move between frames. Scales with resolution and vehicle speed; re-derive from both.",
    ),
    "min_otsu_std_dev": (
        "footage",
        "Rejects flat patches whose Otsu threshold is invented from noise. "
        "Measured: 3.0 lets a false ID 0 through, 5.0+ kills it. Contrast "
        "dependent, so re-derive.",
    ),
    "gray_mode": (
        "footage",
        "Measured, and it FLIPS between dives. 'green' is the best channel at "
        "-6.7 m with the lights off, where red is gone, and the WORST on the "
        "-2.5 m lit pipeline clip, where the pipe and the marker plate are both "
        "yellow and therefore bright in red and green alike -- leaving no "
        "contrast between the plate and the pipe. 'bgr2gray' keeps some blue, "
        "where yellow is dark, and is the only channel that finds the pipeline "
        "marker at all. 'blue' was hypothesised to be ideal and measured worst "
        "on both. Pick per dive from a labelled clip, or run two channels and "
        "take the union.",
    ),
    "use_clahe": (
        "footage",
        "Measured as the single largest false-positive source on this footage. "
        "It is a genuine recall/precision trade, not a free win -- re-measure "
        "BOTH numbers before turning it on.",
    ),
}


# Derived from the 2024 pilot-station screen recordings. See README.
STRUCTURE_2024 = Calibration(
    name="structure_2024",
    source="TAU TAC Challenge 2024 pilot-station recordings, 12-13 Jun 2024, "
    "Visual Inspection (yellow structure). -6.7 m, lights OFF, green "
    "water with the red channel essentially absent. Camera panels only. "
    "Rescaled and double-compressed, so treat every 'footage' number as "
    "provisional.",
    gray_mode="green",
)

PIPELINE_2024 = Calibration(
    name="pipeline_2024",
    source="TAC Challenge pipeline recording, 12 Jun 2024, Pipeline "
    "Inspection. -2.5 to -3.5 m, lights ON, turbid brown-green water "
    "with the red channel intact. One marker visible for 1.2 s of "
    "300 s, so the recall numbers here rest on 14 frames.",
    gray_mode="bgr2gray",
)

# Kept as the default for backwards compatibility; it is the structure profile.
SCREEN_RECORDING_2024 = STRUCTURE_2024


# Metadata, not thresholds -- excluded from every provenance report.
META_FIELDS = frozenset({"name", "source"})


def needs_retune(cal: Calibration = SCREEN_RECORDING_2024) -> list[tuple[str, float, str]]:
    """The fields that must be re-derived when the footage changes."""
    out = []
    for f in fields(cal):
        if f.name in META_FIELDS:
            continue
        kind, why = PROVENANCE.get(f.name, ("footage", "unclassified"))
        if kind == "footage":
            out.append((f.name, getattr(cal, f.name), why))
    return out


def report(cal: Calibration = SCREEN_RECORDING_2024) -> str:
    lines = [f"calibration: {cal.name}", f"source: {cal.source}", ""]
    for kind in ("rules", "physics", "footage"):
        names = [
            f.name
            for f in fields(cal)
            if f.name not in META_FIELDS and PROVENANCE.get(f.name, ("footage", ""))[0] == kind
        ]
        if not names:
            continue
        lines.append(f"-- {kind} --")
        for n in names:
            lines.append(f"  {n:<24} = {getattr(cal, n)}")
        lines.append("")
    lines.append("MUST be re-derived on new footage:")
    for name, val, why in needs_retune(cal):
        lines.append(f"  {name} = {val}")
        lines.append(f"      {why}")
    return "\n".join(lines)


if __name__ == "__main__":
    print(report())
