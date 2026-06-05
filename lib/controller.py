import os
import sys

# fix for error 'NSInternalInconsistencyException', reason: 'nextEventMatchingMask should only be called from the Main Thread on posix systems
if os.name == "posix":
    os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
    os.environ["SDL_VIDEODRIVER"] = "dummy"  # Run pygame without video/window on Linux/MacOS

import copy
import math
import threading
import time

import pygame

if sys.platform.startswith("linux"):
    from pygame._sdl2 import controller as sdl_controller
    from pygame._sdl2 import sdl2
else:
    sdl_controller = None
    sdl2 = None

from lib.bitmask import BitmaskClient


def _use_sdl_gamecontroller():
    return sys.platform.startswith("linux") and sdl_controller is not None


def _controller_errors():
    errors = [pygame.error]
    if sdl2 is not None:
        errors.append(sdl2.error)
    return tuple(errors)


# Controller button bindings: (SDL game-controller button, raw-joystick fallback index).
# Defaults; overridable later via the controller-mapping settings.
FRAME_TOGGLE_BUTTON = pygame.CONTROLLER_BUTTON_B
FRAME_TOGGLE_BUTTON_JS = 1
DOCK_TOGGLE_BUTTON = pygame.CONTROLLER_BUTTON_Y
DOCK_TOGGLE_BUTTON_JS = 3

# Face-down dock-hold targets.
DOCK_PITCH_DEG = 90.0  # nose-down face-down target (sign confirmed in-water)
DOCK_GAIN = 0.5  # precision master gain applied while docked

# Default controller mapping: logical action -> physical input. Each entry has a
# "controller" id (SDL game-controller axis/button) and a "joystick" id (raw
# joystick fallback index); axis actions also carry "invert". These defaults
# reproduce the previously-hardcoded bindings and can be overridden from the
# settings UI (persisted in data/config.json under "controller_map").
DEFAULT_MAPPING = {
    # Stick axes (active when the pitch/roll shift is NOT held)
    "surge": {"type": "axis", "controller": int(pygame.CONTROLLER_AXIS_LEFTY), "joystick": 1, "invert": True},
    "sway": {"type": "axis", "controller": int(pygame.CONTROLLER_AXIS_LEFTX), "joystick": 0, "invert": False},
    "heave": {"type": "axis", "controller": int(pygame.CONTROLLER_AXIS_RIGHTY), "joystick": 3, "invert": True},
    "yaw": {"type": "axis", "controller": int(pygame.CONTROLLER_AXIS_RIGHTX), "joystick": 2, "invert": False},
    # Left stick when the pitch/roll shift IS held
    "pitch": {"type": "axis", "controller": int(pygame.CONTROLLER_AXIS_LEFTY), "joystick": 1, "invert": True},
    "roll": {"type": "axis", "controller": int(pygame.CONTROLLER_AXIS_LEFTX), "joystick": 0, "invert": False},
    # Manipulator open/close (triggers)
    "manip_pos": {"type": "trigger", "controller": int(pygame.CONTROLLER_AXIS_TRIGGERRIGHT), "joystick": 5},
    "manip_neg": {"type": "trigger", "controller": int(pygame.CONTROLLER_AXIS_TRIGGERLEFT), "joystick": 4},
    # Buttons
    "pitchroll_shift": {"type": "button", "controller": int(pygame.CONTROLLER_BUTTON_LEFTSHOULDER), "joystick": 9},
    "dock": {"type": "button", "controller": int(DOCK_TOGGLE_BUTTON), "joystick": DOCK_TOGGLE_BUTTON_JS},
    "frame": {"type": "button", "controller": int(FRAME_TOGGLE_BUTTON), "joystick": FRAME_TOGGLE_BUTTON_JS},
}


class Controller:
    AXIS_THRESHOLDS = {
        "leftx": (0, 0.1),
        "lefty": (1, 0.1),
        "rightx": (2, 0.1),
        "righty": (3, 0.1),
    }

    DEADZONE = 0.05  # Axes within +/- this value are treated as 0
    CONTROLLER_AXIS_MAX = 32767.0
    CONTROLLER_AXIS_MIN = 32768.0
    VISUALIZER_BUTTON_COUNT = 16

    def __init__(self, bitmask_client: BitmaskClient = None, rate_hz: float = 60.0):
        self.bm = bitmask_client  # Use injected bitmask client from app.py
        self.delay_ms = int(1000 / rate_hz) if rate_hz > 0 else 16  # ~60 Hz default
        pygame.init()
        pygame.joystick.init()
        if _use_sdl_gamecontroller():
            sdl_controller.init()
        self.joystick = None
        self.controller = None
        self.axis_offsets = {}  # Calibration offsets for stuck axes
        self.light = 0  # Initial light value
        self._prev_dpad_up = False  # For edge detection of light increase (D-pad up)
        self._prev_dpad_down = False  # For edge detection of light decrease (D-pad down)
        self._stop = threading.Event()
        self._thread = None
        self._reconnect_delay = 0  # Counter for reconnect attempts
        # Debug override state
        self._debug_override = None  # None = no override; dict of axes when active
        self._debug_lock = threading.Lock()
        self._input_status_lock = threading.Lock()
        self._input_status = self._empty_input_status()
        # Gain settings (per-axis and master)
        self._gain_lock = threading.Lock()
        self._master_gain = 1.0
        self._axis_gains = {
            "surge": 1.0,
            "sway": 1.0,
            "heave": 1.0,
            "roll": 1.0,
            "pitch": 1.0,
            "yaw": 1.0,
        }
        # IMU receiver (injected from app.py) for world-frame translation
        self._imu = None
        # Control frame: "rov" (body-relative) or "global" (captured heading)
        self._frame_lock = threading.Lock()
        self._frame_mode = "rov"
        self._ref_yaw = 0.0
        self._prev_frame_button = False
        # Setpoint override client (injected) for face-down dock-hold
        self._override = None
        self._dock_lock = threading.Lock()
        self._docked = False
        self._saved_gains = None
        self._prev_dock_button = False
        # Configurable input mapping (logical action -> physical input)
        self._map_lock = threading.Lock()
        self._mapping = copy.deepcopy(DEFAULT_MAPPING)
        self._try_connect()

    def _try_connect(self):
        """Try to connect to first available joystick without reinitializing subsystem."""
        device_indices = range(pygame.joystick.get_count())
        mapping_preferences = (True, False) if _use_sdl_gamecontroller() else (False,)
        for prefer_controller in mapping_preferences:
            if self._try_connect_matching(device_indices, prefer_controller):
                return True
        return False

    def _try_connect_matching(self, device_indices, prefer_controller):
        for index in device_indices:
            try:
                is_controller = bool(sdl_controller.is_controller(index)) if _use_sdl_gamecontroller() else False
                if is_controller != prefer_controller:
                    continue

                if is_controller:
                    self.controller = sdl_controller.Controller(index)
                    self.joystick = self.controller.as_joystick()
                    print(f"Controller connected: {self.controller.name} (SDL game controller mapping)")
                else:
                    self.controller = None
                    self.joystick = pygame.joystick.Joystick(index)
                    self.joystick.init()
                    print(f"Controller connected: {self.joystick.get_name()} (raw joystick mapping)")

                print(f"  Buttons: {self.joystick.get_numbuttons()}")
                print(f"  Axes: {self.joystick.get_numaxes()}")
                print(f"  Hats: {self.joystick.get_numhats()}")
                self.axis_offsets = {}  # Reset calibration
                if not self.controller:
                    self.calibrate_axes()
                self._update_input_status([0.0] * self.VISUALIZER_BUTTON_COUNT)
                return True
            except _controller_errors() as e:
                print(f"Failed to init joystick {index}: {e}")
                self.controller = None
                self.joystick = None
        return False

    def _disconnect_controller(self):
        """Forget the active input device and stop movement."""
        if self.controller:
            try:
                self.controller.quit()
            except _controller_errors():
                pass
        self.controller = None
        self.joystick = None
        self._reset_command()
        self._set_input_status(self._empty_input_status())

    def _empty_input_status(self):
        return {
            "connected": False,
            "source": "none",
            "name": None,
            "buttons": [0.0] * self.VISUALIZER_BUTTON_COUNT,
            "axes": [],
        }

    def _set_input_status(self, status):
        with self._input_status_lock:
            self._input_status = status

    def get_input_status(self):
        with self._input_status_lock:
            return {
                "connected": self._input_status["connected"],
                "source": self._input_status["source"],
                "name": self._input_status["name"],
                "buttons": list(self._input_status["buttons"]),
                "axes": list(self._input_status.get("axes", [])),
            }

    def calibrate_axes(self):
        """Capture initial axis values to use as offsets (fixes stuck axes)."""
        pygame.event.pump()
        for name, (axis_id, _) in self.AXIS_THRESHOLDS.items():
            if axis_id < self.joystick.get_numaxes():
                initial = self.joystick.get_axis(axis_id)
                # Only apply offset if axis seems stuck (not near zero)
                if abs(initial) > 0.5:
                    self.axis_offsets[axis_id] = initial
                    print(f"  Calibrating {name} (axis {axis_id}): offset {initial:.3f}")

    def get_calibrated_axis(self, axis_id):
        """Get axis value with calibration offset and deadzone applied."""
        raw = self.joystick.get_axis(axis_id)
        offset = self.axis_offsets.get(axis_id, 0)
        calibrated = raw - offset
        # Clamp to -1 to 1 range
        calibrated = max(-1.0, min(1.0, calibrated))
        # Apply deadzone
        if abs(calibrated) < self.DEADZONE:
            return 0.0
        return calibrated

    def _normalize_controller_axis(self, axis_id):
        """Read an SDL GameController axis as a normalized -1.0..1.0 value."""
        raw = self.controller.get_axis(axis_id)
        divisor = self.CONTROLLER_AXIS_MIN if raw < 0 else self.CONTROLLER_AXIS_MAX
        value = max(-1.0, min(1.0, raw / divisor))
        if abs(value) < self.DEADZONE:
            return 0.0
        return value

    def _normalize_controller_trigger(self, axis_id):
        """Read an SDL GameController trigger as a normalized 0.0..1.0 value."""
        raw = self.controller.get_axis(axis_id)
        return max(0.0, min(1.0, raw / self.CONTROLLER_AXIS_MAX))

    def _read_axis(self, controller_axis, joystick_axis):
        if self.controller:
            return self._normalize_controller_axis(controller_axis)
        return self.get_calibrated_axis(joystick_axis)

    def _read_trigger(self, controller_axis, joystick_axis):
        if self.controller:
            return self._normalize_controller_trigger(controller_axis)
        return (self.joystick.get_axis(joystick_axis) + 1) / 2

    def _read_button(self, controller_button, joystick_button):
        if self.controller:
            return bool(self.controller.get_button(controller_button))
        return bool(self.joystick.get_button(joystick_button))

    def _read_dpad_up_down(self):
        if self.controller:
            return (
                bool(self.controller.get_button(pygame.CONTROLLER_BUTTON_DPAD_UP)),
                bool(self.controller.get_button(pygame.CONTROLLER_BUTTON_DPAD_DOWN)),
            )

        hat = self.joystick.get_hat(0) if self.joystick.get_numhats() > 0 else (0, 0)
        return hat[1] > 0, hat[1] < 0

    def _read_visualizer_buttons(self, l2=0.0, r2=0.0):
        buttons = [0.0] * self.VISUALIZER_BUTTON_COUNT

        if self.controller:
            mapping = {
                0: pygame.CONTROLLER_BUTTON_A,
                1: pygame.CONTROLLER_BUTTON_B,
                2: pygame.CONTROLLER_BUTTON_X,
                3: pygame.CONTROLLER_BUTTON_Y,
                4: pygame.CONTROLLER_BUTTON_LEFTSHOULDER,
                5: pygame.CONTROLLER_BUTTON_RIGHTSHOULDER,
                8: pygame.CONTROLLER_BUTTON_BACK,
                9: pygame.CONTROLLER_BUTTON_START,
                10: pygame.CONTROLLER_BUTTON_LEFTSTICK,
                11: pygame.CONTROLLER_BUTTON_RIGHTSTICK,
                12: pygame.CONTROLLER_BUTTON_DPAD_UP,
                13: pygame.CONTROLLER_BUTTON_DPAD_DOWN,
                14: pygame.CONTROLLER_BUTTON_DPAD_LEFT,
                15: pygame.CONTROLLER_BUTTON_DPAD_RIGHT,
            }
            for visualizer_index, controller_button in mapping.items():
                buttons[visualizer_index] = 1.0 if self.controller.get_button(controller_button) else 0.0
        elif self.joystick:
            for index in range(min(self.VISUALIZER_BUTTON_COUNT, self.joystick.get_numbuttons())):
                buttons[index] = 1.0 if self.joystick.get_button(index) else 0.0

        buttons[6] = max(buttons[6], l2)
        buttons[7] = max(buttons[7], r2)
        return buttons

    def _update_input_status(self, buttons, axes=None):
        name = None
        source = "none"
        if self.controller:
            name = self.controller.name
            source = "sdl_gamecontroller"
        elif self.joystick:
            name = self.joystick.get_name()
            source = "raw_joystick"

        self._set_input_status(
            {
                "connected": self.joystick is not None,
                "source": source,
                "name": name,
                "buttons": buttons,
                "axes": axes or [],
            }
        )

    # --- Gain API ---
    def set_gains(self, master=None, **axis_gains):
        """Set master and/or per-axis gains. Values should be 0.0 – 1.0."""
        with self._gain_lock:
            if master is not None:
                self._master_gain = max(0.0, min(1.0, float(master)))
            for key in ("surge", "sway", "heave", "roll", "pitch", "yaw"):
                if key in axis_gains:
                    self._axis_gains[key] = max(0.0, min(1.0, float(axis_gains[key])))

    def get_gains(self):
        """Return current gain settings."""
        with self._gain_lock:
            return {"master": self._master_gain, **self._axis_gains}

    def _apply_gain(self, axis_name, value):
        """Multiply a value by its per-axis gain and the master gain."""
        with self._gain_lock:
            return value * self._axis_gains.get(axis_name, 1.0) * self._master_gain

    # --- Light API ---
    def set_light(self, level):
        """Set light brightness from a normalized 0.0-1.0 level.

        The controller loop owns the light value and resends it every cycle, so
        the web UI drives this same value rather than fighting it. Also pushes
        straight to the bitmask so the change applies even when no joystick is
        connected (and the loop is not calling set_from_axes).
        """
        level = max(0.0, min(1.0, float(level)))
        self.light = level
        if self.bm:
            self.bm.set_command(light=int(round(level * 255)))

    def get_light(self):
        """Return current light brightness as a normalized 0.0-1.0 level."""
        return self.light

    # --- Control frame API ---
    def set_imu(self, imu):
        """Inject the IMU receiver used for world-frame translation."""
        self._imu = imu

    def _current_yaw_fresh(self, max_age_ms=500):
        """Return the latest IMU yaw (deg) if fresh, else None."""
        imu = self._imu
        if imu is None:
            return None
        try:
            stats = imu.get_stats()
        except Exception:
            return None
        age = stats.get("age_ms")
        if age is None or age > max_age_ms:
            return None
        yaw = (stats.get("last_data") or {}).get("yaw")
        try:
            return float(yaw)
        except (TypeError, ValueError):
            return None

    def set_frame_mode(self, mode):
        """Set the control frame ('rov' or 'global'); capture heading on global."""
        mode = "global" if str(mode).lower() == "global" else "rov"
        captured = self._current_yaw_fresh()
        with self._frame_lock:
            self._frame_mode = mode
            if mode == "global":
                self._ref_yaw = captured if captured is not None else 0.0
        return mode

    def toggle_frame_mode(self):
        """Flip between 'rov' and 'global' frames."""
        with self._frame_lock:
            current = self._frame_mode
        return self.set_frame_mode("rov" if current == "global" else "global")

    def get_frame_mode(self):
        with self._frame_lock:
            return self._frame_mode

    def _apply_frame(self, surge, sway):
        """Rotate horizontal translation into the body frame when in global mode.

        Global mode keeps 'forward' pointing at the heading captured when the
        mode was enabled, regardless of how the ROV has since yawed. Falls back
        to ROV (body) frame when the IMU yaw is missing or stale. The rotation
        sign is the single place to flip if in-water testing shows it inverted.
        """
        with self._frame_lock:
            mode = self._frame_mode
            ref = self._ref_yaw
        if mode != "global":
            return surge, sway
        yaw = self._current_yaw_fresh()
        if yaw is None:
            return surge, sway
        delta = math.radians(yaw - ref)
        cos_d = math.cos(delta)
        sin_d = math.sin(delta)
        body_surge = surge * cos_d + sway * sin_d
        body_sway = -surge * sin_d + sway * cos_d
        return body_surge, body_sway

    # --- Face-down dock-hold API ---
    def set_setpoint_override(self, client):
        """Inject the setpoint-override client used to lock attitude for docking."""
        self._override = client

    def dock_engage(self):
        """Lock attitude face-down (pitch + level roll + current heading) and
        apply a precision gain so the pilot can still nudge surge/sway/heave.

        Relies on tuned pitch/roll/yaw PID on the MCU (the override only holds
        attitude if those gains are non-zero).
        """
        captured_yaw = self._current_yaw_fresh()
        axes = {"pitch": DOCK_PITCH_DEG, "roll": 0.0}
        if captured_yaw is not None:
            axes["yaw"] = captured_yaw
        with self._dock_lock:
            if self._override is None:
                return {"ok": False, "error": "Setpoint override client unavailable"}
            try:
                self._override.send_override(axes, replay_attempts=5, replay_delay=0.1)
            except Exception as exc:  # noqa: BLE001 - surface any send failure to caller
                return {"ok": False, "error": str(exc)}
            if not self._docked:
                self._saved_gains = self.get_gains()
            self.set_gains(master=DOCK_GAIN)
            self._docked = True
        return {"ok": True, "docked": True, "setpoints": axes}

    def dock_release(self):
        """Clear the attitude lock and restore the pre-dock gains."""
        with self._dock_lock:
            if self._override is not None:
                try:
                    self._override.clear_override()
                except Exception:  # noqa: BLE001 - release should always succeed locally
                    pass
            if self._saved_gains:
                saved = self._saved_gains
                self.set_gains(
                    master=saved.get("master"),
                    **{k: saved[k] for k in ("surge", "sway", "heave", "roll", "pitch", "yaw") if k in saved},
                )
                self._saved_gains = None
            self._docked = False
        return {"ok": True, "docked": False}

    def dock_toggle(self):
        """Engage dock-hold if released, otherwise release it."""
        with self._dock_lock:
            docked = self._docked
        return self.dock_release() if docked else self.dock_engage()

    def is_docked(self):
        with self._dock_lock:
            return self._docked

    # --- Controller mapping API ---
    def get_mapping(self):
        with self._map_lock:
            return copy.deepcopy(self._mapping)

    def set_mapping(self, mapping):
        """Merge overrides into the input mapping. Unknown actions are ignored."""
        if isinstance(mapping, dict):
            with self._map_lock:
                for action, entry in mapping.items():
                    if action not in self._mapping or not isinstance(entry, dict):
                        continue
                    current = self._mapping[action]
                    for key in ("controller", "joystick"):
                        if key in entry:
                            try:
                                current[key] = int(entry[key])
                            except (TypeError, ValueError):
                                pass
                    if "invert" in current and "invert" in entry:
                        current["invert"] = bool(entry["invert"])
        return self.get_mapping()

    def reset_mapping(self):
        with self._map_lock:
            self._mapping = copy.deepcopy(DEFAULT_MAPPING)
        return self.get_mapping()

    def _map_entry(self, action):
        with self._map_lock:
            return dict(self._mapping.get(action) or DEFAULT_MAPPING[action])

    def _mapped_axis(self, action):
        m = self._map_entry(action)
        val = self._read_axis(m["controller"], m["joystick"])
        return -val if m.get("invert") else val

    def _mapped_trigger(self, action):
        m = self._map_entry(action)
        return self._read_trigger(m["controller"], m["joystick"])

    def _mapped_button(self, action):
        m = self._map_entry(action)
        return self._read_button(m["controller"], m["joystick"])

    def _read_all_axes(self):
        """Snapshot normalized raw axis values for the press-to-bind UI."""
        axes = []
        try:
            if self.controller:
                for i in range(6):  # SDL game controller: LX, LY, RX, RY, TL, TR
                    axes.append(round(self.controller.get_axis(i) / self.CONTROLLER_AXIS_MAX, 3))
            elif self.joystick:
                for i in range(self.joystick.get_numaxes()):
                    axes.append(round(self.joystick.get_axis(i), 3))
        except _controller_errors():
            pass
        return axes

    def _reset_command(self):
        """Reset all axes to neutral/zero."""
        if self.bm:
            self.bm.set_from_axes(
                surge=0,
                sway=0,
                heave=0,
                roll=0,
                pitch=0,
                yaw=0,
                light=self.light,  # Keep light at current level
                manip=0,
            )

    # --- Debug override API ---
    def set_debug_override(self, axes: dict):
        """Enable debug override with the given axis values."""
        with self._debug_lock:
            self._debug_override = dict(axes)

    def clear_debug_override(self):
        """Disable debug override; return to physical controller."""
        with self._debug_lock:
            self._debug_override = None
        self._reset_command()

    def update(self):
        # --- Check for debug override first ---
        with self._debug_lock:
            override = self._debug_override.copy() if self._debug_override is not None else None
        if override is not None:
            # Debug sliders have priority – send their values directly
            if self.bm:
                self.bm.set_from_axes(
                    surge=override.get("surge", 0),
                    sway=override.get("sway", 0),
                    heave=override.get("heave", 0),
                    roll=override.get("roll", 0),
                    pitch=override.get("pitch", 0),
                    yaw=override.get("yaw", 0),
                    light=self.light,
                    manip=0,
                )
            self._set_input_status(
                {
                    "connected": self.joystick is not None,
                    "source": "debug_override",
                    "name": self.joystick.get_name() if self.joystick else None,
                    "buttons": [0.0] * self.VISUALIZER_BUTTON_COUNT,
                    "axes": [],
                }
            )
            return  # Skip all joystick processing

        # Process pygame events (needed for hotplug detection)
        try:
            for event in pygame.event.get():
                if event.type == pygame.JOYDEVICEADDED:
                    print("Joystick device added!")
                    if not self.joystick:
                        self._try_connect()
                elif event.type == pygame.JOYDEVICEREMOVED:
                    print("Joystick device removed!")
                    self._disconnect_controller()
                elif event.type == pygame.CONTROLLERDEVICEADDED:
                    print("Controller device added!")
                    if not self.joystick:
                        self._try_connect()
                elif event.type == pygame.CONTROLLERDEVICEREMOVED:
                    print("Controller device removed!")
                    self._disconnect_controller()
        except SystemError:
            # pygame event system can error during hotplug, just continue
            pass

        # Try to reconnect if no joystick (with delay to avoid spam)
        if not self.joystick:
            self._reconnect_delay += 1
            if self._reconnect_delay >= 60:  # Try every ~1 second
                self._reconnect_delay = 0
                self._try_connect()
            self._set_input_status(self._empty_input_status())
            return

        # Check if joystick is still connected
        try:
            if self.controller:
                if not self.controller.attached():
                    raise pygame.error("controller detached")
            else:
                _ = self.joystick.get_axis(0)
        except _controller_errors():
            print("Controller disconnected!")
            self._reconnect_delay = 0
            self._disconnect_controller()
            return

        # --- BITMASK OUTPUT ----
        # Read axes via the configurable mapping (invert is baked into _mapped_axis)
        heave = self._mapped_axis("heave")
        yaw = self._mapped_axis("yaw")
        # manip is the open trigger minus the close trigger
        r2 = self._mapped_trigger("manip_pos")
        l2 = self._mapped_trigger("manip_neg")
        manip = r2 - l2

        # Holding the pitch/roll shift remaps the left stick from surge/sway to pitch/roll
        left_shoulder = self._mapped_button("pitchroll_shift")
        if left_shoulder:  # Pitch and roll control
            pitch = self._mapped_axis("pitch")
            roll = self._mapped_axis("roll")
            surge = 0.0
            sway = 0.0
        else:  # Surge and sway control
            surge = self._mapped_axis("surge")
            sway = self._mapped_axis("sway")
            pitch = 0.0
            roll = 0.0

        # Light control with edge detection via D-pad up/down
        dpad_up, dpad_down = self._read_dpad_up_down()
        buttons = self._read_visualizer_buttons(l2=l2, r2=r2)

        if dpad_up and not self._prev_dpad_up:  # Just pressed
            self.light = min(1.0, self.light + 0.1)  # +10% per press
        if dpad_down and not self._prev_dpad_down:  # Just pressed
            self.light = max(0, self.light - 0.1)  # -10% per press

        self._prev_dpad_up = dpad_up
        self._prev_dpad_down = dpad_down

        # Frame toggle (edge-detected): switch between ROV and global frames
        frame_pressed = self._mapped_button("frame")
        if frame_pressed and not self._prev_frame_button:
            self.toggle_frame_mode()
        self._prev_frame_button = frame_pressed

        # Dock-hold toggle (edge-detected): lock/unlock face-down attitude
        dock_pressed = self._mapped_button("dock")
        if dock_pressed and not self._prev_dock_button:
            self.dock_toggle()
        self._prev_dock_button = dock_pressed

        self._update_input_status(buttons, self._read_all_axes())

        # Apply gain to each axis
        surge = self._apply_gain("surge", surge)
        sway = self._apply_gain("sway", sway)
        heave = self._apply_gain("heave", heave)
        roll = self._apply_gain("roll", roll)
        pitch = self._apply_gain("pitch", pitch)
        yaw = self._apply_gain("yaw", yaw)

        # World/global frame: rotate horizontal translation by IMU yaw if enabled
        surge, sway = self._apply_frame(surge, sway)

        # Send to ROV!
        if self.bm:
            self.bm.set_from_axes(
                surge=surge, sway=sway, yaw=yaw, pitch=pitch, heave=heave, roll=roll, light=self.light, manip=manip
            )

    def run_loop(self):
        """Blocking loop that polls controller at ~60 Hz."""
        while not self._stop.is_set():
            self.update()
            time.sleep(self.delay_ms / 1000)

    def start(self):
        """Start the controller loop in a background thread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self.run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop the controller loop."""
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.0)
