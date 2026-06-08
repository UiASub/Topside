from flask import Flask

from routes import register_routes


class FakeController:
    def __init__(self):
        self.state = {
            "setpoint_deg": 0.0,
            "setpoint_norm": 0.0,
            "source": "neutral",
            "updated_at": 100.0,
        }

    def set_manipulator(self, setpoint_deg, source="gui"):
        deg = max(-50.0, min(50.0, float(setpoint_deg)))
        self.state = {
            "setpoint_deg": deg,
            "setpoint_norm": deg / 50.0,
            "source": source,
            "updated_at": 100.0,
        }
        return self.state

    def get_manipulator(self):
        return dict(self.state)


class FakeTelemetry:
    def get_latest(self):
        return {
            "timestamp": 100.0,
            "manipulator": {"deg": 12.5, "pulse_us": 1625},
        }


def make_client():
    app = Flask(__name__)
    app.config["CONTROLLER"] = FakeController()
    app.config["CONTROL_TELEM"] = FakeTelemetry()
    register_routes(app)
    return app.test_client()


def test_manipulator_api_returns_target_and_applied_values():
    client = make_client()

    res = client.get("/api/manipulator")

    assert res.status_code == 200
    data = res.get_json()
    assert data["target_deg"] == 0.0
    assert data["applied_deg"] == 12.5
    assert data["pulse_us"] == 1625


def test_manipulator_api_sets_clamped_target():
    client = make_client()

    res = client.post("/api/manipulator", json={"setpoint_deg": 80})

    assert res.status_code == 200
    data = res.get_json()
    assert data["target_deg"] == 50.0
    assert data["source"] == "gui"
