import pygame
from lib.bitmask import BitmaskClient
import threading


class Controller:
    AXIS_THRESHOLDS = {
        "leftx":  (0, 0.1),
        "lefty":  (1, 0.1),
        "rightx": (2, 0.1),
        "righty": (3, 0.1),
    }

    def __init__(self, bitmask_client: BitmaskClient = None, rate_hz: float = 60.0):
        self.bm = bitmask_client  # Use injected bitmask client from app.py
        self.delay_ms = int(1000 / rate_hz) if rate_hz > 0 else 16  # ~60 Hz default
        pygame.init()
        pygame.joystick.init()
        self.joystick = None
        self.axis_offsets = {}  # Calibration offsets for stuck axes
        self.light = 0  # Initial light value
        self._prev_btn_14 = False  # For edge detection of light increase
        self._prev_btn_13 = False  # For edge detection of light decrease
        self._stop = threading.Event()
        self._thread = None
        self._reconnect_delay = 0  # Counter for reconnect attempts
        self._try_connect()
        
    def _try_connect(self):
        """Try to connect to first available joystick without reinitializing subsystem."""
        if pygame.joystick.get_count() > 0:
            try:
                self.joystick = pygame.joystick.Joystick(0)
                self.joystick.init()
                print(f"Controller connected: {self.joystick.get_name()}")
                print(f"  Buttons: {self.joystick.get_numbuttons()}")
                print(f"  Axes: {self.joystick.get_numaxes()}")
                print(f"  Hats: {self.joystick.get_numhats()}")
                self.axis_offsets = {}  # Reset calibration
                self.calibrate_axes()
                return True
            except pygame.error as e:
                print(f"Failed to init joystick: {e}")
                self.joystick = None
                return False
        return False

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
        """Get axis value with calibration offset applied."""
        raw = self.joystick.get_axis(axis_id)
        offset = self.axis_offsets.get(axis_id, 0)
        calibrated = raw - offset
        # Clamp to -1 to 1 range
        return max(-1.0, min(1.0, calibrated))
    
    def _reset_command(self):
        """Reset all axes to neutral/zero."""
        if self.bm:
            self.bm.set_from_axes(
                surge=0, sway=0, heave=0,
                roll=0, pitch=0, yaw=0,
                light=self.light,  # Keep light at current level
                manip=0
            )

    def update(self):
        # Process pygame events (needed for hotplug detection)
        try:
            for event in pygame.event.get():
                if event.type == pygame.JOYDEVICEADDED:
                    print("Joystick device added!")
                    if not self.joystick:
                        self._try_connect()
                elif event.type == pygame.JOYDEVICEREMOVED:
                    print("Joystick device removed!")
                    self.joystick = None
                    self._reset_command() # Stop movement if disconnected
        except SystemError:
            # pygame event system can error during hotplug, just continue
            pass

        # Try to reconnect if no joystick (with delay to avoid spam)
        if not self.joystick:
            self._reconnect_delay += 1
            if self._reconnect_delay >= 60:  # Try every ~1 second
                self._reconnect_delay = 0
                self._try_connect()
            return
        
        # Check if joystick is still connected
        try:
            _ = self.joystick.get_axis(0)
        except pygame.error:
            print("Controller disconnected!")
            self.joystick = None
            self._reconnect_delay = 0
            self._reset_command() # Stop movement if disconnected
            return

        # --- BITMASK OUTPUT ----
        # Read axes
        heave = -self.get_calibrated_axis(3)   # Right Y (inverted)
        yaw = self.get_calibrated_axis(2)      # Right X
        # manip is r2 axis minus l2 axis
        # Triggers: convert from -1..1 to 0..1
        r2 = (self.joystick.get_axis(5) + 1) / 2  # R2 trigger
        l2 = (self.joystick.get_axis(4) + 1) / 2  # L2 trigger
        manip = r2 - l2

        # This runs while button 9 is held down L1 to make 
        # surge and sway controls toggleable to pitch and roll
        if self.joystick.get_button(9):  # Pitch and roll control
            pitch = -self.get_calibrated_axis(1)  # Left Y (inverted)
            roll = self.get_calibrated_axis(0)    # Left X
            surge = 0.0
            sway = 0.0
        else:  # Surge and sway control
            surge = -self.get_calibrated_axis(1)  # Right Y (inverted)
            sway = self.get_calibrated_axis(0)    # Right X
            pitch = 0.0
            roll = 0.0
        
        # Light control with edge detection (only triggers once per press)
        btn_14 = self.joystick.get_button(14)
        btn_13 = self.joystick.get_button(13)
        
        if btn_14 and not self._prev_btn_14:  # Just pressed
            self.light = min(1.0, self.light + 0.1)  # +10% per press
        if btn_13 and not self._prev_btn_13:  # Just pressed
            self.light = max(0, self.light - 0.1)    # -10% per press
        
        self._prev_btn_14 = btn_14
        self._prev_btn_13 = btn_13

        # Send to ROV!
        self.bm.set_from_axes(
            surge=surge,
            sway=sway,
            yaw=yaw,
            pitch=pitch,
            heave=heave,
            roll=roll,
            light=self.light,
            manip=manip
        )
 
    def run_loop(self):
        """Blocking loop that polls controller at ~60 Hz."""
        while not self._stop.is_set():
            self.update()
            pygame.time.delay(self.delay_ms)

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