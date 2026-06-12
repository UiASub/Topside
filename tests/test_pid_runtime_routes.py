from flask import Flask

import routes
from routes import register_routes


class FakeController:
    def __init__(self):
        self.killed = False
        self.pid_enabled = False
        self.setpoints = {}
        self.rates = {"roll": 90.0, "pitch": 90.0, "yaw": 90.0}

    def get_control_state(self):
        return {
            "killed": self.killed,
            "pid_enabled": self.pid_enabled,
            "pid_setpoints": dict(self.setpoints),
            "active_setpoints": dict(self.setpoints) if self.pid_enabled else {},
            "control_path": "KILLED" if self.killed else "PS4",
            "override_active": False,
            "manual_command_before_pid": {},
            "topside_command": {},
        }

    def get_input_status(self):
        return {"connected": False, "source": "none", "name": None, "buttons": []}

    def get_manipulator(self):
        return {"setpoint_norm": 0.0}

    def is_killed(self):
        return self.killed

    def is_pid_enabled(self):
        return self.pid_enabled

    def kill(self):
        self.killed = True
        self.pid_enabled = False
        self.setpoints = {}
        return self.get_control_state()

    def rearm(self):
        self.killed = False
        self.pid_enabled = False
        self.setpoints = {}
        return self.get_control_state()

    def set_debug_override(self, axes):
        return not self.killed

    def clear_debug_override(self):
        pass

    def apply_manual_axes_once(self, axes, source="HTTP"):
        return {axis: 0.0 for axis in routes.CONTROL_AXES} if self.killed else dict(axes)

    def start_pid(self, setpoints):
        self.pid_enabled = True
        self.setpoints = dict(setpoints)
        return dict(self.setpoints)

    def stop_pid(self, clear=True):
        self.pid_enabled = False
        if clear:
            self.setpoints = {}
        return self.get_control_state()

    def set_pid_setpoints(self, setpoints):
        self.setpoints.update(setpoints)
        return dict(self.setpoints)

    def clear_pid_setpoint(self, axis):
        self.setpoints.pop(axis, None)
        if self.pid_enabled and not self.setpoints:
            self.pid_enabled = False
        return dict(self.setpoints)

    def get_pid_setpoints(self):
        return dict(self.setpoints)

    def set_pid_rates(self, rates):
        self.rates.update(rates)
        return dict(self.rates)


class FakeSetpointOverride:
    def __init__(self):
        self.sent = []
        self.clear_count = 0

    def clear_override(self):
        self.clear_count += 1
        return {"active": False, "axes": {}}

    def send_override(self, axes, replay_attempts=3, replay_delay=0.05):
        self.sent.append(dict(axes))
        return {"active": True, "axes": dict(axes)}

    def get_state(self):
        return {"active": bool(self.sent), "axes": self.sent[-1] if self.sent else {}}

    def set_error(self, message):
        self.error = message


class FakeIMU:
    def __init__(self, age_ms=10, data=None):
        self.age_ms = age_ms
        self.data = data or {"roll": 1.0, "pitch": 2.0, "yaw": 3.0}

    def get_stats(self):
        return {"age_ms": self.age_ms, "last_data": dict(self.data)}


class FakeBitmask:
    def __init__(self):
        self.axes = {}

    def set_from_axes(self, **kwargs):
        self.axes.update(kwargs)

    def get_command(self):
        return dict(self.axes)

    def get_uplink_status(self):
        return {"sequence": 1, "last_packet_hex": "00", "last_ack_age_ms": 5}


def make_client(ctrl=None, imu=None, override=None):
    app = Flask(__name__)
    app.config["CONTROLLER"] = ctrl or FakeController()
    app.config["IMU"] = imu or FakeIMU()
    app.config["SETPOINT_OVERRIDE"] = override or FakeSetpointOverride()
    app.config["BITMASK"] = FakeBitmask()
    register_routes(app)
    return app.test_client(), app.config["CONTROLLER"], app.config["SETPOINT_OVERRIDE"]


def test_pid_start_returns_sanity_failure_then_allows_force():
    client, ctrl, override = make_client(imu=FakeIMU(age_ms=3000))

    res = client.post("/api/pid/start", json={})
    assert res.status_code == 409
    assert res.get_json()["force_supported"] is True

    res = client.post("/api/pid/start", json={"force": True})
    assert res.status_code == 200
    data = res.get_json()
    assert data["forced"] is True
    assert ctrl.pid_enabled is True
    assert data["setpoints"] == {"roll": 1.0, "pitch": 2.0, "yaw": 3.0}
    assert override.sent[-1] == {"roll": 1.0, "pitch": 2.0, "yaw": 3.0}


def test_setpoints_save_without_starting_pid_or_sending_override():
    client, ctrl, override = make_client()

    res = client.post("/api/pid/setpoints", json={"roll": 45.0})

    assert res.status_code == 200
    data = res.get_json()
    assert data["pid_active"] is False
    assert ctrl.pid_enabled is False
    assert ctrl.setpoints == {"roll": 45.0}
    assert override.sent == []


def test_pid_start_uses_saved_setpoints_and_current_imu_for_missing_axes():
    client, ctrl, override = make_client()
    client.post("/api/pid/setpoints", json={"roll": 45.0})

    res = client.post("/api/pid/start", json={})

    assert res.status_code == 200
    data = res.get_json()
    assert ctrl.pid_enabled is True
    assert data["setpoints"] == {"roll": 45.0, "pitch": 2.0, "yaw": 3.0}
    assert override.sent[-1] == {"roll": 45.0, "pitch": 2.0, "yaw": 3.0}


def test_active_pid_setpoints_still_update_override():
    ctrl = FakeController()
    ctrl.start_pid({"roll": 10.0})
    override = FakeSetpointOverride()
    client, _ctrl, _override = make_client(ctrl=ctrl, override=override)

    res = client.post("/api/pid/setpoints", json={"yaw": -20.0})

    assert res.status_code == 200
    data = res.get_json()
    assert data["pid_active"] is True
    assert ctrl.setpoints == {"roll": 10.0, "yaw": -20.0}
    assert override.sent[-1] == {"roll": 10.0, "yaw": -20.0}


def test_stop_pid_can_keep_saved_setpoints():
    ctrl = FakeController()
    ctrl.start_pid({"roll": 10.0, "pitch": 20.0})
    override = FakeSetpointOverride()
    client, _ctrl, _override = make_client(ctrl=ctrl, override=override)

    res = client.post("/api/pid/stop", json={"clear": False})

    assert res.status_code == 200
    assert ctrl.pid_enabled is False
    assert ctrl.setpoints == {"roll": 10.0, "pitch": 20.0}
    assert override.clear_count == 1


def test_killswitch_zeroes_pid_gains_and_blocks_debug_override_until_rearm(monkeypatch):
    captured = {}

    def fake_send_pid_gains(gains, timeout=1.0, max_retries=3):
        captured["gains"] = gains
        captured["timeout"] = timeout
        captured["max_retries"] = max_retries
        return gains, 1

    monkeypatch.setattr(routes, "send_pid_gains", fake_send_pid_gains)
    client, _ctrl, _override = make_client()

    res = client.post("/api/control/killswitch")
    assert res.status_code == 200
    data = res.get_json()
    assert data["state"]["killed"] is True
    assert data["pid_gains_zeroed"] is True
    assert captured["gains"] == {axis: {"kp": 0.0, "ki": 0.0, "kd": 0.0} for axis in routes.PID_AXES}

    res = client.post("/api/debug/override", json={"surge": 1})
    assert res.status_code == 423

    res = client.post("/api/control/rearm")
    assert res.status_code == 200
    assert res.get_json()["state"]["killed"] is False


def test_clear_pid_axis_clears_all_then_resends_remaining():
    ctrl = FakeController()
    ctrl.start_pid({"roll": 10.0, "pitch": 20.0, "yaw": 30.0})
    override = FakeSetpointOverride()
    client, _ctrl, _override = make_client(ctrl=ctrl, override=override)

    res = client.delete("/api/pid/setpoints/roll")

    assert res.status_code == 200
    data = res.get_json()
    assert data["remaining"] == {"pitch": 20.0, "yaw": 30.0}
    assert override.clear_count == 1
    assert override.sent[-1] == {"pitch": 20.0, "yaw": 30.0}


def test_pid_gains_force_translation_axes_to_zero(monkeypatch):
    captured = {}

    def fake_send_pid_gains(gains, timeout=1.0, max_retries=3):
        captured["gains"] = gains
        return gains, 1

    monkeypatch.setattr(routes, "send_pid_gains", fake_send_pid_gains)
    client, _ctrl, _override = make_client()

    res = client.post(
        "/api/pid/gains",
        json={
            "surge": {"kp": 9, "ki": 9, "kd": 9},
            "roll": {"kp": 1.0, "ki": 2.0, "kd": 3.0},
        },
    )

    assert res.status_code == 200
    assert captured["gains"]["surge"] == {"kp": 0.0, "ki": 0.0, "kd": 0.0}
    assert captured["gains"]["sway"] == {"kp": 0.0, "ki": 0.0, "kd": 0.0}
    assert captured["gains"]["heave"] == {"kp": 0.0, "ki": 0.0, "kd": 0.0}
    assert captured["gains"]["roll"] == {"kp": 1.0, "ki": 2.0, "kd": 3.0}
    assert set(res.get_json()["gains"].keys()) == {"roll", "pitch", "yaw"}
