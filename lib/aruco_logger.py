import json
import threading
import time
from collections import deque
from datetime import UTC, datetime
from pathlib import Path

from lib.runtime_paths import log_path

ARUCO_LOG = log_path("aruco_markers.ndjson")


class ArucoPipelineLogger:
    """Tracks ordered ARUCO sightings for the pipeline challenge."""

    def __init__(self, log_file=None, confirmation_hits=6, confirmation_window_sec=2.0):
        self._lock = threading.Lock()
        self._enabled = False
        self._entries = []
        self._logged_ids = set()
        self._visible_ids = []
        self._pending = {}
        self._duplicate_count = 0
        self.confirmation_hits = max(1, int(confirmation_hits))
        self.confirmation_window_sec = max(0.1, float(confirmation_window_sec))
        self.log_file = Path(log_file) if log_file is not None else ARUCO_LOG
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

    def start(self):
        with self._lock:
            if not self._enabled:
                self._pending = {}
            self._enabled = True
            snapshot = self._snapshot_locked()
        self._append_log_event({"event": "start", "seen_at": _format_timestamp(time.time())})
        return snapshot

    def stop(self):
        with self._lock:
            self._enabled = False
            snapshot = self._snapshot_locked()
        self._append_log_event({"event": "stop", "seen_at": _format_timestamp(time.time())})
        return snapshot

    def clear(self):
        with self._lock:
            self._entries = []
            self._logged_ids = set()
            self._visible_ids = []
            self._pending = {}
            self._duplicate_count = 0
            snapshot = self._snapshot_locked()
        self._append_log_event({"event": "clear", "seen_at": _format_timestamp(time.time())})
        return snapshot

    def record_visible(self, detections):
        ordered = _ordered_unique_detections(detections)
        now = time.time()
        new_entries = []

        with self._lock:
            self._visible_ids = [marker["id"] for marker in ordered]
            if not self._enabled:
                return self._snapshot_locked()

            self._prune_pending_locked(now)
            for marker in ordered:
                marker_id = marker["id"]
                if marker_id in self._logged_ids:
                    self._duplicate_count += 1
                    continue
                pending = self._pending.setdefault(
                    marker_id,
                    {
                        "first_seen_at": now,
                        "last_seen_at": now,
                        "last_center": _format_center(marker.get("center")),
                        "sightings": deque(),
                    },
                )
                pending["sightings"].append(now)
                pending["last_seen_at"] = now
                pending["last_center"] = _format_center(marker.get("center"))
                if len(pending["sightings"]) < self.confirmation_hits:
                    continue
                self._logged_ids.add(marker_id)
                entry = {
                    "order": len(self._entries) + 1,
                    "id": marker_id,
                    "seen_at": _format_timestamp(now),
                    "first_seen_at": _format_timestamp(pending["first_seen_at"]),
                    "confirmed_hits": len(pending["sightings"]),
                    "confirmation_window_sec": self.confirmation_window_sec,
                    "center": pending["last_center"],
                }
                self._entries.append(entry)
                new_entries.append(entry)
                del self._pending[marker_id]
            snapshot = self._snapshot_locked()
        for entry in new_entries:
            self._append_log_event({"event": "marker", **entry})
        return snapshot

    def snapshot(self):
        with self._lock:
            return self._snapshot_locked()

    def _append_log_event(self, event):
        try:
            with self.log_file.open("a", encoding="utf-8") as fp:
                fp.write(json.dumps(event) + "\n")
        except OSError as exc:
            print(f"ARUCO logger: failed to write log: {exc}")

    def _prune_pending_locked(self, now):
        cutoff = now - self.confirmation_window_sec
        expired_ids = []
        for marker_id, pending in self._pending.items():
            sightings = pending["sightings"]
            while sightings and sightings[0] < cutoff:
                sightings.popleft()
            if sightings:
                pending["first_seen_at"] = sightings[0]
            else:
                expired_ids.append(marker_id)
        for marker_id in expired_ids:
            del self._pending[marker_id]

    def _snapshot_locked(self):
        return {
            "enabled": self._enabled,
            "entries": list(self._entries),
            "visible_ids": list(self._visible_ids),
            "pending": [
                {
                    "id": marker_id,
                    "hits": len(pending["sightings"]),
                    "required_hits": self.confirmation_hits,
                    "last_seen_at": _format_timestamp(pending["last_seen_at"]),
                    "center": pending["last_center"],
                }
                for marker_id, pending in sorted(self._pending.items())
            ],
            "duplicate_count": self._duplicate_count,
            "confirmation_hits": self.confirmation_hits,
            "confirmation_window_sec": self.confirmation_window_sec,
            "log_file": str(self.log_file),
        }


def _ordered_unique_detections(detections):
    ordered = sorted(
        detections,
        key=lambda marker: (
            marker.get("center", (float("inf"), float("inf")))[0],
            marker.get("id", 0),
        ),
    )
    unique = []
    seen_ids = set()
    for marker in ordered:
        marker_id = marker["id"]
        if marker_id in seen_ids:
            continue
        unique.append(marker)
        seen_ids.add(marker_id)
    return unique


def _format_center(center):
    if center is None:
        return None
    return [float(center[0]), float(center[1])]


def _format_timestamp(timestamp):
    return datetime.fromtimestamp(timestamp, UTC).isoformat().replace("+00:00", "Z")
