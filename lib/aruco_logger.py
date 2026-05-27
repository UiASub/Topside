import threading
import time
from datetime import UTC, datetime


class ArucoPipelineLogger:
    """Tracks ordered ARUCO sightings for the pipeline challenge."""

    def __init__(self):
        self._lock = threading.Lock()
        self._enabled = False
        self._entries = []
        self._logged_ids = set()
        self._visible_ids = []
        self._duplicate_count = 0

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
            self._duplicate_count = 0
            return self._snapshot_locked()

    def record_visible(self, detections):
        ordered = sorted(
            detections,
            key=lambda marker: (
                marker.get("center", (float("inf"), float("inf")))[0],
                marker.get("id", 0),
            ),
        )
        now = time.time()

        with self._lock:
            self._visible_ids = [marker["id"] for marker in ordered]
            if not self._enabled:
                return self._snapshot_locked()

            for marker in ordered:
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

    def _snapshot_locked(self):
        return {
            "enabled": self._enabled,
            "entries": list(self._entries),
            "visible_ids": list(self._visible_ids),
            "duplicate_count": self._duplicate_count,
        }


def _format_timestamp(timestamp):
    return datetime.fromtimestamp(timestamp, UTC).isoformat().replace("+00:00", "Z")
