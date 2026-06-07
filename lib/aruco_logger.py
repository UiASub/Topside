import csv
import io
import threading
import time
from datetime import UTC, datetime

MIN_REGION_SCALE = 0.2
MAX_REGION_SCALE = 1.0
DEFAULT_REGION_SCALE = 0.7


class ArucoPipelineLogger:
    """Tracks ordered ARUCO sightings for the pipeline challenge."""

    def __init__(self, region_scale=DEFAULT_REGION_SCALE, marker_overlay_enabled=True):
        self._lock = threading.Lock()
        self._enabled = False
        self._entries = []
        self._logged_ids = set()
        self._visible_ids = []
        self._outside_ids = []
        self._duplicate_count = 0
        self._region_scale = _coerce_region_scale(region_scale)
        self._marker_overlay_enabled = bool(marker_overlay_enabled)

    def start(self):
        with self._lock:
            self._enabled = True
            return self._snapshot_locked()

    def stop(self):
        with self._lock:
            self._enabled = False
            return self._snapshot_locked()

    def clear(self):
        with self._lock:
            self._entries = []
            self._logged_ids = set()
            self._visible_ids = []
            self._outside_ids = []
            self._duplicate_count = 0
            return self._snapshot_locked()

    def set_region_scale(self, scale):
        with self._lock:
            self._region_scale = _coerce_region_scale(scale)
            return self._snapshot_locked()

    def set_marker_overlay_enabled(self, enabled):
        with self._lock:
            self._marker_overlay_enabled = bool(enabled)
            return self._snapshot_locked()

    def marker_overlay_enabled(self):
        with self._lock:
            return self._marker_overlay_enabled

    def region_for_frame(self, frame_shape):
        with self._lock:
            scale = self._region_scale
        return _region_for_frame(frame_shape, scale)

    def record_visible(self, detections, frame_shape=None):
        ordered = sorted(
            detections,
            key=lambda marker: (
                marker.get("center", (float("inf"), float("inf")))[0],
                marker.get("id", 0),
            ),
        )
        now = time.time()

        with self._lock:
            region = _region_for_frame(frame_shape, self._region_scale)
            inside = [marker for marker in ordered if _marker_inside_region(marker, region)]
            outside = [marker for marker in ordered if not _marker_inside_region(marker, region)]
            self._visible_ids = [marker["id"] for marker in inside]
            self._outside_ids = [marker["id"] for marker in outside]
            if not self._enabled:
                return self._snapshot_locked()

            for marker in inside:
                marker_id = marker["id"]
                if marker_id in self._logged_ids:
                    self._duplicate_count += 1
                    continue
                self._logged_ids.add(marker_id)
                self._entries.append(
                    {
                        "order": len(self._entries) + 1,
                        "id": marker_id,
                        "seen_at": _format_timestamp(now),
                    }
                )
            return self._snapshot_locked()

    def snapshot(self):
        with self._lock:
            return self._snapshot_locked()

    def to_csv(self):
        with self._lock:
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=["order", "id", "seen_at"], lineterminator="\n")
            writer.writeheader()
            writer.writerows(self._entries)
            return output.getvalue()

    def _snapshot_locked(self):
        return {
            "enabled": self._enabled,
            "entries": list(self._entries),
            "visible_ids": list(self._visible_ids),
            "outside_ids": list(self._outside_ids),
            "duplicate_count": self._duplicate_count,
            "region_scale": self._region_scale,
            "marker_overlay_enabled": self._marker_overlay_enabled,
        }


def _format_timestamp(timestamp):
    return datetime.fromtimestamp(timestamp, UTC).isoformat().replace("+00:00", "Z")


def _coerce_region_scale(scale):
    try:
        value = float(scale)
    except (TypeError, ValueError):
        value = DEFAULT_REGION_SCALE
    return min(MAX_REGION_SCALE, max(MIN_REGION_SCALE, value))


def _region_for_frame(frame_shape, scale):
    if frame_shape is None:
        return None
    height, width = int(frame_shape[0]), int(frame_shape[1])
    if height <= 0 or width <= 0:
        return None
    region_width = max(1, int(round(width * scale)))
    region_height = max(1, int(round(height * scale)))
    x = max(0, (width - region_width) // 2)
    y = max(0, (height - region_height) // 2)
    return {"x": x, "y": y, "width": region_width, "height": region_height}


def _marker_inside_region(marker, region):
    if region is None:
        return True
    center = marker.get("center")
    if center is None or len(center) < 2:
        return False
    x, y = center[0], center[1]
    return (
        region["x"] <= x <= region["x"] + region["width"]
        and region["y"] <= y <= region["y"] + region["height"]
    )
