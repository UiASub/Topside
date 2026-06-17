import json

from lib.aruco_logger import ArucoPipelineLogger


def test_aruco_logger_ignores_detections_until_started(tmp_path):
    logger = ArucoPipelineLogger(log_file=tmp_path / "aruco_markers.ndjson")

    snapshot = logger.record_visible([{"id": 4, "center": (10, 20)}])

    assert snapshot["enabled"] is False
    assert snapshot["entries"] == []
    assert snapshot["visible_ids"] == [4]


def test_aruco_logger_records_new_markers_left_to_right_once(tmp_path):
    logger = ArucoPipelineLogger(log_file=tmp_path / "aruco_markers.ndjson")
    logger.start()

    detections = [
        {"id": 2, "center": (200, 100)},
        {"id": 1, "center": (100, 100)},
    ]

    snapshot = logger.record_visible(detections)
    assert snapshot["entries"] == []
    assert [candidate["id"] for candidate in snapshot["pending"]] == [1, 2]

    logger.record_visible(detections)
    snapshot = logger.record_visible(detections)

    assert [entry["id"] for entry in snapshot["entries"]] == [1, 2]
    assert [entry["order"] for entry in snapshot["entries"]] == [1, 2]
    assert snapshot["visible_ids"] == [1, 2]
    assert snapshot["pending"] == []

    snapshot = logger.record_visible(
        [
            {"id": 1, "center": (150, 100)},
            {"id": 2, "center": (250, 100)},
        ]
    )

    assert [entry["id"] for entry in snapshot["entries"]] == [1, 2]
    assert snapshot["duplicate_count"] == 2


def test_aruco_logger_clear_resets_logged_ids(tmp_path):
    logger = ArucoPipelineLogger(log_file=tmp_path / "aruco_markers.ndjson")
    logger.start()
    for _ in range(3):
        logger.record_visible([{"id": 8, "center": (0, 0)}])

    snapshot = logger.clear()
    assert snapshot["entries"] == []
    assert snapshot["visible_ids"] == []
    assert snapshot["pending"] == []
    assert snapshot["duplicate_count"] == 0

    logger.start()
    for _ in range(2):
        logger.record_visible([{"id": 8, "center": (0, 0)}])
    snapshot = logger.record_visible([{"id": 8, "center": (0, 0)}])
    assert [entry["id"] for entry in snapshot["entries"]] == [8]


def test_aruco_logger_tolerates_underwater_flicker(tmp_path):
    logger = ArucoPipelineLogger(log_file=tmp_path / "aruco_markers.ndjson")
    logger.start()

    logger.record_visible([{"id": 6, "center": (10, 20)}])
    logger.record_visible([])
    logger.record_visible([{"id": 6, "center": (12, 21)}])
    logger.record_visible([])
    snapshot = logger.record_visible([{"id": 6, "center": (14, 22)}])

    assert [entry["id"] for entry in snapshot["entries"]] == [6]
    assert snapshot["entries"][0]["confirmed_hits"] == 3
    assert snapshot["entries"][0]["center"] == [14.0, 22.0]


def test_aruco_logger_writes_events_to_file(tmp_path):
    log_file = tmp_path / "aruco_markers.ndjson"
    logger = ArucoPipelineLogger(log_file=log_file)

    snapshot = logger.start()
    detections = [
        {"id": 12, "center": (120, 100)},
        {"id": 10, "center": (20, 100)},
    ]
    for _ in range(3):
        logger.record_visible(detections)
    logger.record_visible([{"id": 10, "center": (30, 100)}])
    logger.clear()
    logger.stop()

    events = [json.loads(line) for line in log_file.read_text(encoding="utf-8").splitlines()]
    marker_events = [event for event in events if event["event"] == "marker"]

    assert snapshot["log_file"] == str(log_file)
    assert [event["event"] for event in events] == ["start", "marker", "marker", "clear", "stop"]
    assert [event["id"] for event in marker_events] == [10, 12]
    assert [event["order"] for event in marker_events] == [1, 2]
    assert marker_events[0]["confirmed_hits"] == 3
