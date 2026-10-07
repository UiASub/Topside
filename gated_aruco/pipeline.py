"""The gated detector: OpenCV decode, then a stack of independent checks.

Design rule: a candidate is killed by exactly one gate -- the first that
rejects it -- and that gate is recorded. That makes "measure what each one
kills" a property of the pipeline rather than something you reconstruct
afterwards.

To measure a gate's *independent* contribution, run the harness with that gate
as the only one enabled. To measure its *marginal* contribution, run with the
full stack minus that gate. Both are one config change.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Literal

import cv2
import numpy as np

from .gates import Candidate, FrameContext, TemporalConfirmer
from .params import get_dictionary

GrayMode = Literal["bgr2gray", "green", "blue", "green_blue_max", "value"]


def to_gray(bgr: np.ndarray, mode: GrayMode = "bgr2gray") -> np.ndarray:
    """Build the single-channel image the decoder works on.

    Underwater, red is attenuated first and carries mostly backscatter noise,
    so the standard 0.299R + 0.587G + 0.114B mix spends 30% of its weight on
    the worst channel. That reasoning is sound, and it is not the whole story:
    MEASURED, the best channel turns out to be a property of the dive.

    Fraction of sampled frames in which the known real marker was detected,
    tuned parameters throughout:

        channel           structure clip          pipeline clip
                        -6.7 m, lights OFF     -2.5 m, lights ON
                          (red gone)             (red intact)
        bgr2gray        1/3  ->  2/3 w/CLAHE    0/3  ->  1/3 w/CLAHE
        green           2/3  ->  3/3 w/CLAHE    0/3  ->  0/3
        blue            1/3  ->  0/3 w/CLAHE    0/3  ->  0/3
        green_blue_max  2/3  ->  3/3 w/CLAHE    0/3  ->  0/3
        value           2/3  ->  3/3 w/CLAHE    0/3  ->  0/3

    - "green" is the clear winner at depth with the lights off, where red is
      simply absent (70% of pixels have R exactly 0) and the scene is green.
    - "green" is the WORST option on the shallow lit pipeline clip. There red
      survives, and the pipe and the marker's plate are both yellow -- bright
      in red and green alike -- so the green channel has almost no contrast
      between the white plate and the pipe behind it. Only bgr2gray, which
      keeps some blue where yellow is dark, finds anything at all.
    - "blue" was hypothesised here to be good for exactly that reason: a yellow
      structure is dark in blue while the marker's white cells stay bright.
      Measured, it is the worst channel on both clips. On the deep clip there
      is too little blue signal left to threshold; on the shallow turbid clip
      blue backscatter dominates. The hypothesis was wrong.

    So: do not hardcode a channel. Pick it per dive from a labelled clip, or
    run two channels and take the union -- they fail in different conditions,
    which is the useful property.
    """
    if mode == "bgr2gray":
        return cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    if mode == "blue":
        return bgr[:, :, 0].copy()
    if mode == "green":
        return bgr[:, :, 1].copy()
    if mode == "green_blue_max":
        return np.maximum(bgr[:, :, 0], bgr[:, :, 1])
    if mode == "value":
        return cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)[:, :, 2].copy()
    raise ValueError(f"unknown gray mode: {mode}")


def apply_clahe(gray: np.ndarray, clip: float = 2.0, tile_px: int = 320) -> np.ndarray:
    """Local contrast equalisation, with a RESOLUTION-INDEPENDENT tile size.

    CLAHE raises recall on dim distant markers *and* raises the false-positive
    rate, because it amplifies the noise inside dark grate holes into something
    Otsu will happily binarise. Measure both numbers before adopting it.

    The `tile_px` argument is the fix for a trap that cost a real marker.
    OpenCV's `tileGridSize` is a GRID COUNT, so an 8x8 grid means something
    different on every frame size: 320 px tiles on a 2556 px frame, 214 px
    tiles on a 1708 px crop of the same scene. Tuning on one and deploying on
    the other silently changes the preprocessing.

    That is not hypothetical. The pipeline clip's one real marker, over the
    30 frames it is visible, detected with tuned parameters:

        gray      CLAHE             full 2556px frame   1708px camera panel
        bgr2gray  off                         0                  0
        bgr2gray  clip 2.0, grid 8x8         10                  0
        bgr2gray  clip 2.0, grid 5x5          1                  7
        green     clip 2.0, grid 5x5          1                  8

    Same clip, same marker, same parameters -- found ten times or zero times
    depending on a grid constant. The grids that worked were 8x8 on 2556 px and
    5x5 on 1708 px: 320 px and 342 px tiles respectively. Holding the tile's
    field of view fixed at roughly 320 px reproduces both.

    This matters for shipping because Topside detects on the raw camera frame,
    while everything in this repo was measured on screen recordings at a
    different resolution. Specifying the tile in pixels is what lets a
    measured configuration transfer.
    """
    h, w = gray.shape[:2]
    gx = max(1, int(round(w / max(1, tile_px))))
    gy = max(1, int(round(h / max(1, tile_px))))
    return cv2.createCLAHE(clipLimit=clip, tileGridSize=(gx, gy)).apply(gray)


@dataclass
class PipelineConfig:
    dictionary_name: str = "DICT_ARUCO_ORIGINAL"
    gray_mode: GrayMode = "bgr2gray"
    clahe: bool = False
    clahe_clip: float = 2.0
    clahe_tile_px: int = 320


@dataclass
class FrameResult:
    frame_index: int
    confirmed: list[Candidate] = field(default_factory=list)
    rejected: list[tuple[Candidate, str]] = field(default_factory=list)
    raw_decoded: int = 0


class GatedArucoDetector:
    def __init__(
        self,
        detector_params,
        gates: list,
        config: PipelineConfig | None = None,
        temporal: TemporalConfirmer | None = None,
    ):
        self.config = config or PipelineConfig()
        self.dictionary = get_dictionary(self.config.dictionary_name)
        self.detector = cv2.aruco.ArucoDetector(self.dictionary, detector_params)
        self.gates = gates
        self.temporal = temporal
        self.stats: Counter[str] = Counter()
        self._frame_index = -1

    def reset(self) -> None:
        self.stats.clear()
        self._frame_index = -1
        if self.temporal is not None:
            self.temporal.reset()

    def process(self, bgr: np.ndarray) -> FrameResult:
        self._frame_index += 1
        gray = to_gray(bgr, self.config.gray_mode)
        if self.config.clahe:
            gray = apply_clahe(gray, self.config.clahe_clip, self.config.clahe_tile_px)

        corners, ids, _rejected = self.detector.detectMarkers(gray)
        result = FrameResult(frame_index=self._frame_index)

        if ids is None or len(ids) == 0:
            return result

        ctx = FrameContext(bgr=bgr, gray=gray, frame_index=self._frame_index)
        result.raw_decoded = len(ids)
        self.stats["raw_decoded"] += len(ids)

        survivors: list[Candidate] = []
        for marker_id, quad in zip(ids.flatten(), corners, strict=False):
            cand = Candidate(
                marker_id=int(marker_id),
                corners=np.asarray(quad, dtype=np.float32).reshape(4, 2),
            )
            killed_by = None
            for gate in self.gates:
                verdict = gate(cand, ctx)
                if not verdict.passed:
                    killed_by = f"{gate.name}:{verdict.reason}"
                    break
            if killed_by is None:
                survivors.append(cand)
            else:
                self.stats[killed_by] += 1
                result.rejected.append((cand, killed_by))

        if self.temporal is not None:
            confirmed, pending = self.temporal.update(self._frame_index, survivors)
            for cand, reason in pending:
                self.stats[f"temporal:{reason}"] += 1
                result.rejected.append((cand, f"temporal:{reason}"))
            result.confirmed = confirmed
        else:
            result.confirmed = survivors

        self.stats["confirmed"] += len(result.confirmed)
        return result


def draw(bgr: np.ndarray, result: FrameResult, show_rejected: bool = True) -> np.ndarray:
    out = bgr.copy()
    if show_rejected:
        for cand, reason in result.rejected:
            pts = cand.corners.astype(np.int32)
            cv2.polylines(out, [pts], True, (60, 60, 200), 1)
            cv2.putText(
                out,
                reason.split(":")[-1][:22],
                tuple(pts[0]),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.35,
                (60, 60, 200),
                1,
                cv2.LINE_AA,
            )
    for cand in result.confirmed:
        pts = cand.corners.astype(np.int32)
        cv2.polylines(out, [pts], True, (0, 230, 90), 2)
        cv2.putText(
            out,
            f"ID {cand.marker_id}",
            tuple(pts[0] + np.array([0, -6])),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 230, 90),
            2,
            cv2.LINE_AA,
        )
    return out
