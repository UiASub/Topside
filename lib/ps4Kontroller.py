import pygame
import os
from bitmask import init_bitmask

class Controller:
    AXIS_THRESHOLDS = {
        "leftx":  (0, 0.1),
        "lefty":  (1, 0.1),
        "rightx": (2, 0.1),
        "righty": (3, 0.1),
        "L2":     (4, 0.1),  # L2 trigger (some systems)
        "R2":     (5, 0.1),  # R2 trigger (some systems)
    }

    def __init__(self):
        self.bm = init_bitmask() #initialize bitmask client
        pygame.init()
        pygame.joystick.init()
        self.joystick = None
        self.axis_offsets = {}  # Calibration offsets for stuck axes
        self.connect_joystick()
        

    def connect_joystick(self):
        if pygame.joystick.get_count() > 0:
            self.joystick = pygame.joystick.Joystick(0)
            self.joystick.init()
            print("PS4 Controller connected.")
            print(f"  Buttons: {self.joystick.get_numbuttons()}")
            print(f"  Axes: {self.joystick.get_numaxes()}")
            print(f"  Hats: {self.joystick.get_numhats()}")
            self.calibrate_axes()
        else:
            print("No PS4 Controller found.")

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

    def update(self):
        pygame.event.pump()

        if not self.joystick:
            return

        output_parts = []

        # ---- KNAPPER (only when pressed) ----
        pressed_buttons = []
        for i in range(self.joystick.get_numbuttons()):
            if self.joystick.get_button(i):
                pressed_buttons.append(str(i))
        if pressed_buttons:
            output_parts.append(f"BTN[{','.join(pressed_buttons)}]")

        # ---- AKSER (always show all) ----
        axis_parts = []
        for name, (axis_id, threshold) in self.AXIS_THRESHOLDS.items():
            if axis_id >= self.joystick.get_numaxes():
                axis_parts.append(f"{name}:----")
                continue
            value = self.get_calibrated_axis(axis_id)
            if abs(value) > abs(threshold):
                axis_parts.append(f"{name}:{value:+.2f}")
            else:
                axis_parts.append(f"{name}: 0.00")
        output_parts.append(" ".join(axis_parts))

        # ---- D-PAD (HAT) ----
        for i in range(self.joystick.get_numhats()):
            hat = self.joystick.get_hat(i)
            if hat != (0, 0):
                dirs = []
                if hat[1] == 1: dirs.append("U")
                if hat[1] == -1: dirs.append("D")
                if hat[0] == -1: dirs.append("L")
                if hat[0] == 1: dirs.append("R")
                output_parts.append(f"DPAD[{''.join(dirs)}]")

        # ---- PRINT ALT PÅ EN LINJE ----
        line = " | ".join(output_parts)
        print(f"\r{line:<100}", end='', flush=True)

        # --- BITMASK OUTPUT ----
        # Read axes
        heave = -self.get_calibrated_axis(3)   # Right Y (inverted)
        yaw = self.get_calibrated_axis(2)     # Right X
        # manip is r2 axis minus l2 axis
        r2 = (self.get_calibrated_axis(5) + 1.0) / 2.0  # Normalize 0 to 1
        l2 = (self.get_calibrated_axis(4) + 1.0) / 2.0  # Normalize 0 to 1
        manip = r2-l2

        # This runs while button 9 is held down L1 to make 
        # surge and sway controls toggleable to pitch and roll
        if self.joystick.get_button(9):
            pitch = -self.get_calibrated_axis(1)  # Left Y (inverted)
            roll = self.get_calibrated_axis(0)    # Left X
            surge = 0.0
            sway = 0.0
        else:
            surge = -self.get_calibrated_axis(1)  # Right Y (inverted)
            sway = self.get_calibrated_axis(0)    # Right X
            pitch = 0.0
            roll = 0.0
        
        # Send to ROV!
        self.bm.set_from_axes(
            surge=surge,
            sway=sway,
            yaw=yaw,
            pitch=pitch,
            heave=heave,
            roll=roll,
            light=0.0,
            manip=0.0
        )

        #debug code:
        #cmd = self.bm.get_command()
        #print(f"\n  CMD: surge={cmd['surge']:+4d} sway={cmd['sway']:+4d} heave={cmd['heave']:+4d} "
        #      f"yaw={cmd['yaw']:+4d} pitch={cmd['pitch']:+4d} roll={cmd['roll']:+4d} "
        #      f"manip={cmd['manip']:3d} seq={cmd['sequence']}")

controller = Controller()
while True:
    controller.update()
    pygame.time.delay(100)