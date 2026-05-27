from lib.aruco_logger import ArucoPipelineLogger


def test_aruco_logger_ignores_detections_until_started():
    logger = ArucoPipelineLogger()

    snapshot = logger.record_visible([{"id": 4, "center": (10, 20)}])

    assert snapshot["enabled"] is False
    assert snapshot["entries"] == []
    assert snapshot["visible_ids"] == [4]


def test_aruco_logger_records_new_markers_left_to_right_once():
    logger = ArucoPipelineLogger()
    logger.start()

    snapshot = logger.record_visible(
        [
            {"id": 2, "center": (200, 100)},
            {"id": 1, "center": (100, 100)},
        ]
    )

    assert [entry["id"] for entry in snapshot["entries"]] == [1, 2]
    assert [entry["order"] for entry in snapshot["entries"]] == [1, 2]
    assert snapshot["visible_ids"] == [1, 2]

    snapshot = logger.record_visible(
        [
            {"id": 1, "center": (150, 100)},
            {"id": 2, "center": (250, 100)},
        ]
    )

    assert [entry["id"] for entry in snapshot["entries"]] == [1, 2]
    assert snapshot["duplicate_count"] == 2


def test_aruco_logger_clear_resets_logged_ids():
    logger = ArucoPipelineLogger()
    logger.start()
    logger.record_visible([{"id": 8, "center": (0, 0)}])

    snapshot = logger.clear()
    assert snapshot["entries"] == []
    assert snapshot["visible_ids"] == []
    assert snapshot["duplicate_count"] == 0

    logger.start()
    snapshot = logger.record_visible([{"id": 8, "center": (0, 0)}])
    assert [entry["id"] for entry in snapshot["entries"]] == [8]
