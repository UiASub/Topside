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


def test_aruco_logger_exports_entries_as_csv():
    logger = ArucoPipelineLogger()
    logger.start()
    logger.record_visible([{"id": 12, "center": (0, 0)}])

    lines = logger.to_csv().splitlines()

    assert lines[0] == "order,id,seen_at"
    assert lines[1].startswith("1,12,")


def test_aruco_logger_filters_logging_to_center_region():
    logger = ArucoPipelineLogger(region_scale=0.5)
    logger.start()

    snapshot = logger.record_visible(
        [
            {"id": 1, "center": (50, 50)},
            {"id": 2, "center": (5, 50)},
        ],
        frame_shape=(100, 100),
    )

    assert snapshot["visible_ids"] == [1]
    assert snapshot["outside_ids"] == [2]
    assert [entry["id"] for entry in snapshot["entries"]] == [1]


def test_aruco_logger_clamps_region_scale():
    logger = ArucoPipelineLogger()

    snapshot = logger.set_region_scale(2.0)
    assert snapshot["region_scale"] == 1.0

    snapshot = logger.set_region_scale(0.01)
    assert snapshot["region_scale"] == 0.2


def test_aruco_logger_marker_overlay_defaults_on_and_toggles():
    logger = ArucoPipelineLogger()

    assert logger.snapshot()["marker_overlay_enabled"] is True
    assert logger.marker_overlay_enabled() is True

    snapshot = logger.set_marker_overlay_enabled(False)

    assert snapshot["marker_overlay_enabled"] is False
    assert logger.marker_overlay_enabled() is False
