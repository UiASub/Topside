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
