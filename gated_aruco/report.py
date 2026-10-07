"""Turn confirmed detections into the thing the judges actually score.

The gate stack answers "is this marker real". It does not answer "what do we
hand in", and the two differ in ways worth 50 points.

`ArucoPipelineLogger._logged_ids` in Topside is a `set`. A set is wrong for
both inspection missions, for two different reasons:

**Pipeline Inspection.** The deliverable is an ORDERED list. Beyond +10 per
correct marker there is +25 for reporting them in the right order and +25 for
starting from the pinger end (a mirrored sequence also scores). A set has no
order, so it cannot collect either bonus -- 50 points, a third of a perfect
100-point run, discarded by a data-structure choice. Order of first sighting is
the right proxy: the vehicle flies the pipe from one end, so the order it first
sees markers in is the order they lie in.

**Visual Inspection.** Here "a specific ID may occur more than once", and each
correctly identified marker is scored separately, so a set can cost 20 points
by collapsing two real markers into one. That is the obvious failure and it is
the *less* costly one. The opposite mistake -- treating every detection track
as a new physical marker -- turned the two real markers in the 2024 footage
into seventeen reports, fifteen of them wrong at -10 each, scoring 0 against
40. `distinct_markers()` therefore deduplicates by default and takes evidence,
not enthusiasm, to split.

Both bonuses are robust to detector error, which is worth knowing before
tuning against them. Working the booklet's own example: truth 56,77,5,80,32,
report "56,5,20,32" scores +30 for three correct, -5 for the false 20, and
still collects both +25 bonuses. A false positive between two correct IDs did
not break the order, and a missing marker explicitly does not either.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import tac


@dataclass
class Sighting:
    """One continuous run of confirmed detections of one marker."""

    marker_id: int
    first_frame: int
    last_frame: int
    key: str = ""

    @property
    def span(self) -> int:
        return self.last_frame - self.first_frame + 1


@dataclass
class MissionReport:
    """Accumulates confirmed detections and emits the mission deliverable.

    Feed it only detections that have already passed the gates and temporal
    confirmation. This class does no filtering -- it is bookkeeping, and mixing
    the two is how the confirmation step ends up bypassed.
    """

    mission: str = "pipeline"
    max_gap_frames: int = 45
    _open: dict[str, Sighting] = field(default_factory=dict)
    _closed: list[Sighting] = field(default_factory=list)
    _order: int = 0

    def observe(self, frame_index: int, marker_id: int, key: str | None = None) -> None:
        """Record one confirmed detection.

        `key` distinguishes physical markers that share an ID -- pass the track
        id from the temporal confirmer, or a pose-derived label. Without it,
        two markers with the same ID are indistinguishable and will be merged,
        which on the Visual Inspection structure silently costs a marker.
        """
        k = f"{marker_id}:{key}" if key is not None else str(marker_id)
        s = self._open.get(k)
        if s is not None and frame_index - s.last_frame <= self.max_gap_frames:
            s.last_frame = max(s.last_frame, frame_index)
            return
        if s is not None:
            self._closed.append(s)
        self._open[k] = Sighting(marker_id, frame_index, frame_index, k)

    def sightings(self) -> list[Sighting]:
        out = self._closed + list(self._open.values())
        return sorted(out, key=lambda s: (s.first_frame, s.marker_id))

    # -- deliverables -------------------------------------------------------
    def ordered_ids(self) -> list[int]:
        """The Pipeline Inspection deliverable: IDs in order of first sighting.

        Deduplicated, because the rules say a pipeline ID will not repeat, so a
        second sighting of an ID is the same marker seen again.
        """
        seen: set[int] = set()
        out: list[int] = []
        for s in self.sightings():
            if s.marker_id not in seen:
                seen.add(s.marker_id)
                out.append(s.marker_id)
        return out

    def distinct_markers(self, split_repeats: bool = False) -> list[int]:
        """The Visual Inspection deliverable: one entry per physical marker.

        DEDUPLICATED BY DEFAULT, and the asymmetry that forces it is steep.
        On the structure an ID may genuinely occur twice, and each occurrence
        scores +20 -- so reporting it once costs 20 points. But a spurious
        split costs -10, and splits are spurious far more often than not: a
        marker goes out of frame and comes back as a new track every time the
        vehicle moves.

        Measured on the 2024 structure clips, the two real markers (61 and 89)
        produced 17 tracks. Reporting one entry per track scores:

            2 correct   x +20 = +40
            15 spurious x -10 = -150      ->  0 after the floor

        against 40 for the deduplicated list. Splitting only pays if a repeated
        ID is real more than one time in three, and here it was two in
        seventeen.

        So: `split_repeats=True` requires real evidence that two markers with
        the same ID occupy different physical locations. Track identity is not
        that evidence -- it cannot distinguish "re-acquired after looking away"
        from "a second marker". Pose can. Until PoseGate has calibrated
        intrinsics, leave this alone.
        """
        if split_repeats:
            return [s.marker_id for s in self.sightings()]
        seen: set[int] = set()
        out: list[int] = []
        for s in self.sightings():
            if s.marker_id not in seen:
                seen.add(s.marker_id)
                out.append(s.marker_id)
        return out

    def deliverable(self) -> list[int]:
        if self.mission == "pipeline":
            return self.ordered_ids()
        return self.distinct_markers()

    # -- scoring ------------------------------------------------------------
    def score(self, truth: list[int], ordered: bool | None = None) -> int:
        """Estimated standard points, per the booklet. Floored at zero.

        `truth` is the ground-truth marker list, in pipeline order for the
        pipeline mission.
        """
        rules = tac.PIPELINE_SCORING if self.mission == "pipeline" else tac.VISUAL_INSPECTION_SCORING
        got = self.deliverable()
        remaining = list(truth)
        correct = 0
        for m in got:
            if m in remaining:
                remaining.remove(m)
                correct += 1
        incorrect = len(got) - correct
        points = correct * rules.correct + incorrect * rules.incorrect

        if self.mission == "pipeline":
            hits = [m for m in got if m in truth]
            if ordered is None:
                # A mirrored sequence scores too, per the booklet.
                ordered = _is_subsequence(hits, truth) or _is_subsequence(hits, truth[::-1])

            # The "more than two IDs" / "more than one ID" minima are counted
            # over the CORRECT ids, not over everything reported. That is what
            # reproduces the booklet's own example "1,2,3,4,5": one correct ID
            # among five reported scores 0, not 40. You cannot demonstrate an
            # order with one marker, however long the list is.
            if len(hits) >= tac.PIPELINE_ORDER_MIN_IDS and ordered:
                points += tac.PIPELINE_ORDER_BONUS

            if len(hits) >= tac.PIPELINE_START_MIN_IDS:
                # "the first ID in the sequence is closer to the pinger than
                # the other markers" -- the pinger is at truth[0], so the first
                # reported hit must have the smallest index. Note this is NOT
                # symmetric, even though the order bonus accepts a mirror:
                # example "32,5,77" collects the order bonus and not this one.
                idx = [truth.index(m) for m in hits]
                if idx[0] == min(idx):
                    points += tac.PIPELINE_START_BONUS
        return max(0, points)


def _is_subsequence(small: list[int], big: list[int]) -> bool:
    it = iter(big)
    return all(any(x == y for y in it) for x in small)
