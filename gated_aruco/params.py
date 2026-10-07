"""OpenCV ArucoDetector parameter presets.

Every override below is annotated with the OpenCV default and the reason it is
changed. Nothing here is a guess dressed as a fact: if a knob is listed as
"unchanged" it is because measurement showed it does nothing for this
dictionary, or because it trades recall for precision in a way that has to be
measured on real footage first.
"""

from __future__ import annotations

import cv2

# The dictionary mandated by competition rules.
DICTIONARY_NAME = "DICT_ARUCO_ORIGINAL"


def get_dictionary(name: str = DICTIONARY_NAME):
    return cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, name))


def default_params() -> cv2.aruco.DetectorParameters:
    """Stock OpenCV defaults. This is the baseline to measure against."""
    return cv2.aruco.DetectorParameters()


def tuned_params() -> cv2.aruco.DetectorParameters:
    """Precision-biased parameters for a textured yellow structure."""
    p = cv2.aruco.DetectorParameters()

    # --- Error correction: OFF, and it is live on current OpenCV ------------
    # OpenCV budgets maxCorrectionBits * errorCorrectionRate bits of
    # correction. For DICT_ARUCO_ORIGINAL, measured:
    #   OpenCV 4.11 - 4.13: maxCorrectionBits == 0, the rate multiplies to 0
    #                       and this line is a harmless no-op.
    #   OpenCV 4.14, 5.0  : maxCorrectionBits == 1. The default rate of 0.6
    #                       still rounds the budget to 0, but any rate >= 1.0
    #                       turns on one bit of correction, which inflates each
    #                       of the 4094 accepted patterns into a ball of 26 and
    #                       takes the false-accept rate from 1-in-8196 to
    #                       1-in-315. Twenty-six times worse.
    # Note the boundary is 4.14, not 5.0. A `<5` version pin does not save you.
    # The dictionary has a minimum inter-marker distance of 1 bit, so
    # "correcting" a bit can only ever move you onto a neighbouring legal ID --
    # it never recovers the right answer, only manufactures a confident wrong
    # one. There is no version of this that helps. Pin it to zero.
    p.errorCorrectionRate = 0.0

    # --- Quiet-zone enforcement -------------------------------------------
    # default 0.35, i.e. 35% of the 24 border cells may decode as white.
    # A real marker printed with a proper quiet zone has an all-black border.
    # A grate hole has no border at all, so whatever OpenCV samples there is
    # arbitrary. This is the single strongest stock knob.
    p.maxErroneousBitsInBorderRate = 0.10

    # --- Flat-patch rejection ---------------------------------------------
    # default 5.0. Otsu on a patch with no real bimodality invents a threshold
    # and turns sensor noise into bits. A shadowed grate hole is exactly that.
    p.minOtsuStdDev = 12.0

    # --- Shape plausibility -----------------------------------------------
    p.polygonalApproxAccuracyRate = 0.01  # default 0.03; demand a real quad
    p.minCornerDistanceRate = 0.10  # default 0.05
    p.minMarkerDistanceRate = 0.10  # default 0.05; drop stacked dupes
    p.minDistanceToBorder = 5  # default 3; partial quads are noise

    # --- Size bounds (fractions of max image dimension) --------------------
    # Tighten once you know the real working distance. 0.03 lets a 30px marker
    # through on a 960px frame, which is below the size where 25 bits are
    # readable at all.
    p.minMarkerPerimeterRate = 0.05  # default 0.03
    p.maxMarkerPerimeterRate = 3.0  # default 4.0

    # --- Bit sampling ------------------------------------------------------
    # default 0.13. Sampling closer to each cell's centre stops blur bleed from
    # neighbouring cells flipping a bit.
    p.perspectiveRemoveIgnoredMarginPerCell = 0.25
    p.perspectiveRemovePixelPerCell = 8  # default 4; more pixels per vote

    # --- Adaptive threshold ------------------------------------------------
    # A grate is a high-contrast periodic edge field. A small window locks onto
    # the bar/hole edges and manufactures candidates; a larger floor helps.
    p.adaptiveThreshWinSizeMin = 5  # default 3
    p.adaptiveThreshWinSizeMax = 33  # default 23
    p.adaptiveThreshWinSizeStep = 8  # default 10
    p.adaptiveThreshConstant = 7.0  # default 7.0 (unchanged, measure it)

    # --- Corner refinement -------------------------------------------------
    # Needed for pose gating to mean anything.
    p.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    p.cornerRefinementWinSize = 5
    p.cornerRefinementMaxIterations = 30
    p.cornerRefinementMinAccuracy = 0.05

    # --- Deliberately NOT changed -----------------------------------------
    # detectInvertedMarker: already False. Leave it False; True doubles the
    #   candidate pool for no benefit here.
    return p


PRESETS = {
    "default": default_params,
    "tuned": tuned_params,
}
