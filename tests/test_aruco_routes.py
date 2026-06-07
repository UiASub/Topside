from flask import Flask

from lib.aruco_logger import ArucoPipelineLogger
from routes import register_routes


def _client_with_logger(logger=None):
    app = Flask(__name__)
    app.config["ARUCO_LOGGER"] = logger
    register_routes(app)
    return app.test_client()


def test_aruco_log_routes_control_logger():
    logger = ArucoPipelineLogger()
    client = _client_with_logger(logger)

    res = client.post("/api/aruco-log/start")
    assert res.status_code == 200
    assert res.get_json()["log"]["enabled"] is True

    logger.record_visible([{"id": 5, "center": (10, 10)}])
    res = client.get("/api/aruco-log")
    data = res.get_json()
    assert data["ok"] is True
    assert [entry["id"] for entry in data["log"]["entries"]] == [5]

    res = client.post("/api/aruco-log/clear")
    data = res.get_json()
    assert data["log"]["entries"] == []

    res = client.post("/api/aruco-log/stop")
    assert res.get_json()["log"]["enabled"] is False


def test_aruco_log_routes_report_missing_logger():
    client = _client_with_logger()

    res = client.get("/api/aruco-log")

    assert res.status_code == 503
    assert res.get_json()["ok"] is False


def test_aruco_log_csv_export_downloads_snapshot():
    logger = ArucoPipelineLogger()
    logger.start()
    logger.record_visible([{"id": 5, "center": (10, 10)}])
    client = _client_with_logger(logger)

    res = client.get("/api/aruco-log/export.csv")

    assert res.status_code == 200
    assert res.mimetype == "text/csv"
    assert "attachment" in res.headers["Content-Disposition"]
    assert res.get_data(as_text=True).splitlines()[0] == "order,id,seen_at"
    assert res.get_data(as_text=True).splitlines()[1].startswith("1,5,")


def test_aruco_log_csv_export_reports_missing_logger():
    client = _client_with_logger()

    res = client.get("/api/aruco-log/export.csv")

    assert res.status_code == 503
    assert res.get_json()["ok"] is False


def test_aruco_log_region_route_updates_scale():
    logger = ArucoPipelineLogger()
    client = _client_with_logger(logger)

    res = client.post("/api/aruco-log/region", json={"scale": 0.45})

    assert res.status_code == 200
    data = res.get_json()
    assert data["ok"] is True
    assert data["log"]["region_scale"] == 0.45


def test_aruco_log_region_route_reports_missing_logger():
    client = _client_with_logger()

    res = client.post("/api/aruco-log/region", json={"scale": 0.45})

    assert res.status_code == 503
    assert res.get_json()["ok"] is False


def test_aruco_log_marker_overlay_route_updates_state():
    logger = ArucoPipelineLogger()
    client = _client_with_logger(logger)

    res = client.post("/api/aruco-log/marker-overlay", json={"enabled": False})

    assert res.status_code == 200
    data = res.get_json()
    assert data["ok"] is True
    assert data["log"]["marker_overlay_enabled"] is False


def test_aruco_log_marker_overlay_route_reports_missing_logger():
    client = _client_with_logger()

    res = client.post("/api/aruco-log/marker-overlay", json={"enabled": False})

    assert res.status_code == 503
    assert res.get_json()["ok"] is False
