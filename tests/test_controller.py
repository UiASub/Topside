import os
import threading

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

import pygame
import pytest

import lib.controller as controller_module
from lib.controller import Controller


class FakeBitmask:
    def __init__(self):
        self.calls = []
        self.commands = []

    def set_from_axes(self, **kwargs):
        self.calls.append(kwargs)

    def set_command(self, **kwargs):
        self.commands.append(kwargs)


class FakeSdlController:
    def __init__(self, axes=None, buttons=None, attached=True):
        self.axes = axes or {}
        self.buttons = buttons or set()
        self._attached = attached
        self.name = "fake SDL controller"

    def attached(self):
        return self._attached

    def get_axis(self, axis):
        return self.axes.get(axis, 0)

    def get_button(self, button):
        return button in self.buttons


class FakeJoystick:
    def __init__(self, axes=None, buttons=None, hat=(0, 0)):
        self.axes = axes or {}
        self.buttons = buttons or set()
        self.hat = hat

    def init(self):
        pass

    def get_axis(self, axis):
        return self.axes.get(axis, 0.0)

    def get_button(self, button):
        return button in self.buttons

    def get_numbuttons(self):
        return max(self.buttons, default=-1) + 1

    def get_numaxes(self):
        return max(self.axes, default=-1) + 1

    def get_name(self):
        return "fake joystick"

    def get_numhats(self):
        return 1

    def get_hat(self, index):
        assert index == 0
        return self.hat


def build_controller(controller=None, joystick=None):
    ctrl = Controller.__new__(Controller)
    ctrl.bm = FakeBitmask()
    ctrl.delay_ms = 16
    ctrl.controller = controller
    ctrl.joystick = joystick or FakeJoystick()
    ctrl.axis_offsets = {}
    ctrl.light = 0.0
    ctrl._prev_dpad_up = False
    ctrl._prev_dpad_down = False
    ctrl._manipulator_deg = 0.0
    ctrl._manipulator_source = "neutral"
    ctrl._manipulator_updated = 0.0
    ctrl._manipulator_lock = threading.Lock()
    ctrl._reconnect_delay = 0
    ctrl._debug_override = None
    ctrl._debug_lock = threading.Lock()
    ctrl._input_status_lock = threading.Lock()
    ctrl._input_status = ctrl._empty_input_status()
    ctrl._runtime_lock = threading.RLock()
    ctrl._killed = False
    ctrl._pid_enabled = False
    ctrl._pid_setpoints = {}
    ctrl._pid_setpoint_rates = dict(controller_module.DEFAULT_PID_SETPOINT_RATES)
    ctrl._last_pid_update = 0.0
    ctrl._last_manual_command = {axis: 0.0 for axis in controller_module.CONTROL_AXES}
    ctrl._last_output_command = {axis: 0.0 for axis in controller_module.CONTROL_AXES}
    ctrl._last_runtime_source = "PS4"
    ctrl._last_pid_error = None
    ctrl._setpoint_client = None
    return ctrl


class FakeSetpointClient:
    def __init__(self):
        self.sent = []
        self.errors = []

    def send_override(self, axes, replay_attempts=3, replay_delay=0.05):
        self.sent.append(dict(axes))
        return {"active": True, "axes": dict(axes)}

    def set_error(self, message):
        self.errors.append(message)


def test_sdl_gamecontroller_mapping_normalizes_linux_playstation_layout(monkeypatch):
    monkeypatch.setattr(pygame.event, "get", lambda: [])
    sdl = FakeSdlController(
        axes={
            pygame.CONTROLLER_AXIS_LEFTX: 8192,
            pygame.CONTROLLER_AXIS_LEFTY: -16384,
            pygame.CONTROLLER_AXIS_RIGHTX: 12288,
            pygame.CONTROLLER_AXIS_RIGHTY: -4096,
            pygame.CONTROLLER_AXIS_TRIGGERLEFT: 0,
            pygame.CONTROLLER_AXIS_TRIGGERRIGHT: 32767,
        },
        buttons={pygame.CONTROLLER_BUTTON_DPAD_UP},
    )
    ctrl = build_controller(controller=sdl)

    ctrl.update()

    command = ctrl.bm.calls[-1]
    assert command["surge"] == pytest.approx(0.5, rel=1e-3)
    assert command["sway"] == pytest.approx(0.25, rel=1e-3)
    assert command["heave"] == pytest.approx(0.125, rel=1e-3)
    assert command["yaw"] == pytest.approx(-0.375, rel=1e-3)
    assert command["pitch"] == 0.0
    assert command["roll"] == 0.0
    assert command["manip"] == pytest.approx(-0.0144, rel=1e-3)
    assert command["light"] == pytest.approx(0.1, rel=1e-3)
    status = ctrl.get_input_status()
    assert status["connected"] is True
    assert status["source"] == "sdl_gamecontroller"
    assert status["buttons"][7] == 1.0
    assert status["buttons"][12] == 1.0


def test_sdl_left_shoulder_switches_right_stick_to_pitch_and_roll(monkeypatch):
    monkeypatch.setattr(pygame.event, "get", lambda: [])
    sdl = FakeSdlController(
        axes={
            pygame.CONTROLLER_AXIS_LEFTX: 8192,
            pygame.CONTROLLER_AXIS_LEFTY: -16384,
            pygame.CONTROLLER_AXIS_RIGHTX: -32768,
            pygame.CONTROLLER_AXIS_RIGHTY: 32767,
        },
        buttons={pygame.CONTROLLER_BUTTON_LEFTSHOULDER},
    )
    ctrl = build_controller(controller=sdl)

    ctrl.update()

    command = ctrl.bm.calls[-1]
    assert command["surge"] == pytest.approx(0.5, rel=1e-3)
    assert command["sway"] == pytest.approx(0.25, rel=1e-3)
    assert command["heave"] == 0.0
    assert command["yaw"] == 0.0
    assert command["pitch"] == -1.0
    assert command["roll"] == -1.0
    status = ctrl.get_input_status()
    assert status["buttons"][4] == 1.0


def test_raw_joystick_mapping_remains_available_for_unsupported_devices(monkeypatch):
    monkeypatch.setattr(pygame.event, "get", lambda: [])
    joystick = FakeJoystick(
        axes={
            0: 0.25,
            1: -0.5,
            2: 0.4,
            3: -0.2,
            4: -1.0,
            5: 1.0,
        },
        hat=(0, 1),
    )
    ctrl = build_controller(joystick=joystick)

    ctrl.update()

    command = ctrl.bm.calls[-1]
    assert command["surge"] == 0.5
    assert command["sway"] == 0.25
    assert command["heave"] == 0.2
    assert command["yaw"] == -0.4
    assert command["manip"] == pytest.approx(-0.0144, rel=1e-3)
    assert command["light"] == pytest.approx(0.1, rel=1e-3)
    status = ctrl.get_input_status()
    assert status["source"] == "raw_joystick"
    assert status["buttons"][7] == 1.0


def test_set_light_clamps_and_pushes_to_bitmask():
    ctrl = build_controller()

    ctrl.set_light(0.5)
    assert ctrl.get_light() == pytest.approx(0.5)
    assert ctrl.bm.commands[-1]["light"] == 128

    ctrl.set_light(2.0)  # clamps to MAX_LIGHT -> 204
    assert ctrl.get_light() == ctrl.MAX_LIGHT
    assert ctrl.bm.commands[-1]["light"] == 204

    ctrl.set_light(-1.0)  # clamps to 0.0 -> 0
    assert ctrl.get_light() == 0.0
    assert ctrl.bm.commands[-1]["light"] == 0


def test_set_manipulator_clamps_and_pushes_to_bitmask():
    ctrl = build_controller()

    state = ctrl.set_manipulator(25)
    assert state["setpoint_deg"] == 25
    assert ctrl.bm.commands[-1]["manip"] == 64

    state = ctrl.set_manipulator(100)
    assert state["setpoint_deg"] == 50.0
    assert ctrl.bm.commands[-1]["manip"] == 127

    state = ctrl.set_manipulator(-100)
    assert state["setpoint_deg"] == -50.0
    assert ctrl.bm.commands[-1]["manip"] == -127


def test_l2_nudges_manipulator_counterclockwise(monkeypatch):
    monkeypatch.setattr(pygame.event, "get", lambda: [])
    sdl = FakeSdlController(
        axes={
            pygame.CONTROLLER_AXIS_TRIGGERLEFT: 32767,
            pygame.CONTROLLER_AXIS_TRIGGERRIGHT: 0,
        }
    )
    ctrl = build_controller(controller=sdl)

    ctrl.update()

    command = ctrl.bm.calls[-1]
    assert command["manip"] == pytest.approx(0.0144, rel=1e-3)
    assert ctrl.get_manipulator()["source"] == "controller"


def test_non_linux_connection_uses_raw_joystick_without_sdl_probe(monkeypatch):
    class FailingSdlController:
        @staticmethod
        def is_controller(index):
            raise AssertionError(f"unexpected SDL controller probe for joystick {index}")

    joystick = FakeJoystick()
    ctrl = build_controller(joystick=None)

    monkeypatch.setattr(controller_module.sys, "platform", "win32")
    monkeypatch.setattr(controller_module, "sdl_controller", FailingSdlController)
    monkeypatch.setattr(pygame.joystick, "get_count", lambda: 1)
    monkeypatch.setattr(pygame.joystick, "Joystick", lambda index: joystick)
    monkeypatch.setattr(pygame.event, "pump", lambda: None)

    assert ctrl._try_connect() is True
    assert ctrl.controller is None
    assert ctrl.joystick is joystick
    assert ctrl.get_input_status()["source"] == "raw_joystick"


def test_killswitch_zeroes_axes_and_blocks_manual_commands():
    ctrl = build_controller()

    state = ctrl.kill()
    output = ctrl.apply_manual_axes_once({"surge": 1.0, "roll": 1.0, "yaw": -1.0}, source="HTTP")

    assert state["killed"] is True
    assert state["pid_enabled"] is False
    assert output == {axis: 0.0 for axis in controller_module.CONTROL_AXES}
    assert ctrl.bm.calls[-1]["surge"] == 0
    assert ctrl.bm.calls[-1]["roll"] == 0
    assert ctrl.bm.calls[-1]["yaw"] == 0


def test_rearm_returns_to_ps4_pid_off_neutral_state():
    ctrl = build_controller()
    ctrl.kill()

    state = ctrl.rearm()

    assert state["killed"] is False
    assert state["pid_enabled"] is False
    assert state["control_path"] == "PS4"
    assert state["pid_setpoints"] == {}
    assert ctrl.bm.calls[-1]["surge"] == 0


def test_pid_manual_input_updates_setpoints_and_blocks_rotational_thrust(monkeypatch):
    ctrl = build_controller()
    client = FakeSetpointClient()
    ctrl.set_setpoint_client(client)
    ctrl.set_pid_rates({"roll": 40, "pitch": 40, "yaw": 40})
    ctrl.start_pid({"roll": 170, "pitch": 89, "yaw": 179})
    ctrl._last_pid_update = 100.0
    monkeypatch.setattr(controller_module.time, "monotonic", lambda: 100.5)

    output = ctrl.apply_manual_axes_once(
        {"surge": 0.5, "sway": -0.25, "heave": 0.1, "roll": 1, "pitch": 1, "yaw": 1},
        source="HTTP",
    )

    assert output["surge"] == pytest.approx(0.5)
    assert output["sway"] == pytest.approx(-0.25)
    assert output["heave"] == pytest.approx(0.1)
    assert output["roll"] == 0.0
    assert output["pitch"] == 0.0
    assert output["yaw"] == 0.0
    assert ctrl.get_pid_setpoints() == {"roll": 180.0, "pitch": 90.0, "yaw": -171.0}
    assert client.sent[-1] == {"roll": 180.0, "pitch": 90.0, "yaw": -171.0}


def test_pid_off_allows_direct_rotational_manual_control():
    ctrl = build_controller()
    ctrl.start_pid({"roll": 0, "pitch": 0, "yaw": 0})
    ctrl.stop_pid()

    output = ctrl.apply_manual_axes_once({"roll": 0.4, "pitch": -0.3, "yaw": 0.2}, source="HTTP")

    assert output["roll"] == pytest.approx(0.4)
    assert output["pitch"] == pytest.approx(-0.3)
    assert output["yaw"] == pytest.approx(0.2)
