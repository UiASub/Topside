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
    ctrl.controller = controller
    ctrl.joystick = joystick or FakeJoystick()
    ctrl.axis_offsets = {}
    ctrl.light = 0.0
    ctrl._prev_dpad_up = False
    ctrl._prev_dpad_down = False
    ctrl._reconnect_delay = 0
    ctrl._debug_override = None
    ctrl._debug_lock = threading.Lock()
    ctrl._input_status_lock = threading.Lock()
    ctrl._input_status = ctrl._empty_input_status()
    ctrl._gain_lock = threading.Lock()
    ctrl._master_gain = 1.0
    ctrl._axis_gains = {
        "surge": 1.0,
        "sway": 1.0,
        "heave": 1.0,
        "roll": 1.0,
        "pitch": 1.0,
        "yaw": 1.0,
    }
    ctrl._imu = None
    ctrl._frame_lock = threading.Lock()
    ctrl._frame_mode = "rov"
    ctrl._ref_yaw = 0.0
    ctrl._prev_frame_button = False
    return ctrl


class FakeIMU:
    def __init__(self, yaw=0.0, age_ms=10):
        self.yaw = yaw
        self.age_ms = age_ms

    def get_stats(self):
        return {"age_ms": self.age_ms, "last_data": {"yaw": self.yaw}}


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
    assert command["yaw"] == pytest.approx(0.375, rel=1e-3)
    assert command["pitch"] == 0.0
    assert command["roll"] == 0.0
    assert command["manip"] == 1.0
    assert command["light"] == pytest.approx(0.1, rel=1e-3)
    status = ctrl.get_input_status()
    assert status["connected"] is True
    assert status["source"] == "sdl_gamecontroller"
    assert status["buttons"][7] == 1.0
    assert status["buttons"][12] == 1.0


def test_sdl_left_shoulder_switches_left_stick_to_pitch_and_roll(monkeypatch):
    monkeypatch.setattr(pygame.event, "get", lambda: [])
    sdl = FakeSdlController(
        axes={
            pygame.CONTROLLER_AXIS_LEFTX: -32768,
            pygame.CONTROLLER_AXIS_LEFTY: 32767,
        },
        buttons={pygame.CONTROLLER_BUTTON_LEFTSHOULDER},
    )
    ctrl = build_controller(controller=sdl)

    ctrl.update()

    command = ctrl.bm.calls[-1]
    assert command["surge"] == 0.0
    assert command["sway"] == 0.0
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
    assert command["yaw"] == 0.4
    assert command["manip"] == 1.0
    assert command["light"] == pytest.approx(0.1, rel=1e-3)
    status = ctrl.get_input_status()
    assert status["source"] == "raw_joystick"
    assert status["buttons"][7] == 1.0


def test_set_light_clamps_and_pushes_to_bitmask():
    ctrl = build_controller()

    ctrl.set_light(0.5)
    assert ctrl.get_light() == pytest.approx(0.5)
    assert ctrl.bm.commands[-1]["light"] == 128

    ctrl.set_light(2.0)  # clamps to 1.0 -> 255
    assert ctrl.get_light() == 1.0
    assert ctrl.bm.commands[-1]["light"] == 255

    ctrl.set_light(-1.0)  # clamps to 0.0 -> 0
    assert ctrl.get_light() == 0.0
    assert ctrl.bm.commands[-1]["light"] == 0


def test_rov_frame_is_identity():
    ctrl = build_controller()
    ctrl.set_imu(FakeIMU(yaw=45.0))
    # Default mode is "rov" -> no rotation regardless of yaw.
    assert ctrl._apply_frame(0.7, -0.3) == (0.7, -0.3)


def test_global_frame_rotates_translation_by_relative_yaw():
    ctrl = build_controller()
    imu = FakeIMU(yaw=0.0)
    ctrl.set_imu(imu)
    ctrl.set_frame_mode("global")  # captures ref_yaw = 0
    # ROV has since yawed +90°; world-forward (surge=1) maps onto body axes.
    imu.yaw = 90.0
    body_surge, body_sway = ctrl._apply_frame(1.0, 0.0)
    assert body_surge == pytest.approx(0.0, abs=1e-9)
    assert body_sway == pytest.approx(-1.0, abs=1e-9)


def test_global_frame_falls_back_to_rov_when_imu_stale():
    ctrl = build_controller()
    imu = FakeIMU(yaw=0.0)
    ctrl.set_imu(imu)
    ctrl.set_frame_mode("global")
    imu.yaw = 90.0
    imu.age_ms = 5000  # stale -> no rotation
    assert ctrl._apply_frame(1.0, 0.0) == (1.0, 0.0)


def test_toggle_frame_mode_flips_between_rov_and_global():
    ctrl = build_controller()
    ctrl.set_imu(FakeIMU(yaw=0.0))
    assert ctrl.get_frame_mode() == "rov"
    assert ctrl.toggle_frame_mode() == "global"
    assert ctrl.get_frame_mode() == "global"
    assert ctrl.toggle_frame_mode() == "rov"


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
