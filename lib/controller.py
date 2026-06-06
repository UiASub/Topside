import os
import sys

# fix for error 'NSInternalInconsistencyException', reason: 'nextEventMatchingMask should only be called from the Main Thread on posix systems
if os.name == "posix":
    os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
    os.environ["SDL_VIDEODRIVER"] = "dummy"  # Run pygame without video/window on Linux/MacOS

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

    # Hard cap on light brightness (normalized 0.0-1.0). Enforced for every
    # input path (D-pad, web slider, debug slider) so brightness can never
    # exceed this regardless of where the request comes from.
    MAX_LIGHT = 0.8

    # Raw-joystick D-pad fallback: some controllers (e.g. DualShock 4 on
    # Windows) expose the D-pad as buttons instead of a hat. Verified mapping.
    DPAD_UP_BUTTON = 11
    DPAD_DOWN_BUTTON = 12

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

        if self.joystick.get_numhats() > 0:
            hat = self.joystick.get_hat(0)
            return hat[1] > 0, hat[1] < 0

        # No hat (e.g. DualShock 4 on Windows): D-pad is exposed as buttons.
        num_buttons = self.joystick.get_numbuttons()
        up = self.DPAD_UP_BUTTON < num_buttons and bool(self.joystick.get_button(self.DPAD_UP_BUTTON))
        down = self.DPAD_DOWN_BUTTON < num_buttons and bool(self.joystick.get_button(self.DPAD_DOWN_BUTTON))
        return up, down

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

    def _update_input_status(self, buttons):
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
        level = max(0.0, min(self.MAX_LIGHT, float(level)))
        self.light = level
        if self.bm:
            self.bm.set_command(light=int(round(level * 255)))

    def get_light(self):
        """Return current light brightness as a normalized 0.0-1.0 level."""
        return self.light

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
        # Read axes
        heave = -self._read_axis(pygame.CONTROLLER_AXIS_RIGHTY, 3)  # Right Y (inverted)
        yaw = self._read_axis(pygame.CONTROLLER_AXIS_RIGHTX, 2)  # Right X
        # manip is r2 axis minus l2 axis
        r2 = self._read_trigger(pygame.CONTROLLER_AXIS_TRIGGERRIGHT, 5)  # R2 trigger
        l2 = self._read_trigger(pygame.CONTROLLER_AXIS_TRIGGERLEFT, 4)  # L2 trigger
        manip = r2 - l2

        # This runs while button 9 is held down L1 to make
        # surge and sway controls toggleable to pitch and roll
        left_shoulder = self._read_button(pygame.CONTROLLER_BUTTON_LEFTSHOULDER, 9)
        if left_shoulder:  # Pitch and roll control
            pitch = -self._read_axis(pygame.CONTROLLER_AXIS_LEFTY, 1)  # Left Y (inverted)
            roll = self._read_axis(pygame.CONTROLLER_AXIS_LEFTX, 0)  # Left X
            surge = 0.0
            sway = 0.0
        else:  # Surge and sway control
            surge = -self._read_axis(pygame.CONTROLLER_AXIS_LEFTY, 1)  # Left Y (inverted)
            sway = self._read_axis(pygame.CONTROLLER_AXIS_LEFTX, 0)  # Left X
            pitch = 0.0
            roll = 0.0

        # Light control with edge detection via D-pad up/down
        dpad_up, dpad_down = self._read_dpad_up_down()
        buttons = self._read_visualizer_buttons(l2=l2, r2=r2)

        if dpad_up and not self._prev_dpad_up:  # Just pressed
            self.light = min(self.MAX_LIGHT, self.light + 0.1)  # +10% per press
        if dpad_down and not self._prev_dpad_down:  # Just pressed
            self.light = max(0, self.light - 0.1)  # -10% per press

        self._prev_dpad_up = dpad_up
        self._prev_dpad_down = dpad_down
        self._update_input_status(buttons)

        # Apply gain to each axis
        surge = self._apply_gain("surge", surge)
        sway = self._apply_gain("sway", sway)
        heave = self._apply_gain("heave", heave)
        roll = self._apply_gain("roll", roll)
        pitch = self._apply_gain("pitch", pitch)
        yaw = self._apply_gain("yaw", yaw)

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
