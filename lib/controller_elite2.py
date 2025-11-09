import os
import math
import socket
import struct
import time
import pygame

# ===================== Config =====================
UDP_IP   = os.getenv("ROV_IP",   "192.168.2.50")
UDP_PORT = int(os.getenv("ROV_UDP_PORT", "9000"))
RATE_HZ  = int(os.getenv("ROV_RATE_HZ", "60"))

# Deadzone tuning
RADIAL_DZ       = float(os.getenv("RADIAL_DZ", "0.0"))   # keep available, but default off
AXIS_DZ         = float(os.getenv("AXIS_DZ", "0.10"))    # per-axis threshold: no input until > 0.10
ANTI_DZ         = float(os.getenv("ANTI_DZ", "0.06"))     # pushes small input past DZ
EXPO            = float(os.getenv("EXPO", "0.25"))        # 0 = linear, 0.2–0.4 is nice
MAX_DELTA_PER_T = int(os.getenv("MAX_DELTA_PER_T", "120"))  # i16 units per tick

# Startup center calibration
CALIBRATION_SEC = float(os.getenv("CALIBRATION_SEC", "0.8"))

# ===================== Bitfield layout (uint16) =====================
BIT = {
    # Modes (right face cluster)
    "MODE_MANUAL":       0,   # B
    "MODE_DEPTH":        1,   # Y
    "MODE_STAB":         2,   # X
    # Camera tilt
    "CAM_TILT_UP":       3,   # RB
    "CAM_TILT_DN":       4,   # LB
    "CAM_TILT_CENTER":   5,   # L3 (left stick press)
    # Utilities per diagram (D-pad + RS)
    "GAIN_INC":          6,   # D-pad Up
    "GAIN_DEC":          7,   # D-pad Down
    "LIGHTS_DIM":        8,   # D-pad Left
    "LIGHTS_BRIGHT":     9,   # D-pad Right
    "TOGGLE_INPUT_HOLD": 10,  # R3 (right stick press)
    "SHIFT":             11,  # A (used as a modifier if you want)
    # Reserved / high bits
    "ARM":               14,  # Menu/Start
    "DISARM":            15,  # View/Back
}

# ===================== Helpers =====================

def _axis_to_i16(v: float) -> int:
    v = max(-1.0, min(1.0, v))
    return int(round(v * 1000))

def _expo(v: float, e: float) -> float:
    if e <= 1e-6: return v
    return math.copysign(abs(v) ** (1.0 + e), v)

def _radial_deadzone(x: float, y: float, dz: float):
    r = math.sqrt(x*x + y*y)
    if r < dz:
        return 0.0, 0.0
    scale = (r - dz) / (1.0 - dz)
    if r > 1e-6:
        x = (x / r) * scale
        y = (y / r) * scale
    return x, y

def _axis_deadzone(v: float, dz: float) -> float:
    """Per-axis deadzone: zero under threshold, rescale remainder to full range."""
    a = abs(v)
    if a < dz:
        return 0.0
    # rescale so that dz maps to 0 and 1 maps to 1
    return math.copysign((a - dz) / (1.0 - dz), v)

def _apply_antidz(v: float, adz: float) -> float:
    if v == 0.0: return 0.0
    return math.copysign(min(1.0, abs(v) + adz), v)

def _rate_limit(prev: int, new: int, max_step: int) -> int:
    if max_step <= 0: return new
    delta = new - prev
    if delta >  max_step: return prev + max_step
    if delta < -max_step: return prev - max_step
    return new

# ===================== Main class =====================

class Elite2ControllerSender:
    """
    Xbox Elite/Series controller via pygame (SDL). Mapping matches the diagram:
      - Left stick: surge (forward/back), sway (left/right)
      - Right stick: yaw (left/right), heave (up/down)
      - RB/LB: camera tilt up/down, L3: tilt center
      - A=SHIFT, B=Manual, X=Stabilize, Y=Depth
      - D-pad: up/down = gain +/- ; left/right = lights dim/bright
      - R3: Toggle Input Hold
      - Menu(Start)=ARM, View(Back)=DISARM
    """

    def __init__(self, ip=UDP_IP, port=UDP_PORT):
        self.addr = (ip, port)
        self.seq  = 0
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        pygame.init()
        pygame.joystick.init()

        if pygame.joystick.get_count() == 0:
            raise RuntimeError("No controller detected")

        # Prefer Xbox/Elite/Series names
        chosen = 0
        for i in range(pygame.joystick.get_count()):
            name = pygame.joystick.Joystick(i).get_name().lower()
            if "elite" in name or "xbox" in name or "microsoft" in name or "series" in name:
                chosen = i
                break

        self.j = pygame.joystick.Joystick(chosen)
        self.j.init()
        self.name = self.j.get_name()
        print(f"[Controller] Connected: {self.name} (axes={self.j.get_numaxes()}, buttons={self.j.get_numbuttons()}, hats={self.j.get_numhats()})")

        # ---- Axis indices (macOS mapping: 0=LX,1=LY,2=RX,3=RY; triggers=4,5) ----
        self.AX_LX, self.AX_LY, self.AX_RX, self.AX_RY = 0, 1, 2, 3

        # ---- Button indices (SDL on macOS) ----
        # A=0, B=1, X=2, Y=3, LB=4, RB=5, View/Back=8, Menu/Start=9, LS=10, RS=11
        self.BTN_A, self.BTN_B, self.BTN_X, self.BTN_Y = 0, 1, 2, 3
        self.BTN_LB, self.BTN_RB = 4, 5
        self.BTN_VIEW, self.BTN_MENU = 8, 9
        self.BTN_LS, self.BTN_RS = 10, 11

        # Paddles often appear 12..15 (we mirror helpful actions onto them)
        self.paddle_btns = []
        nb = self.j.get_numbuttons()
        for idx in range(12, min(16, nb)):
            self.paddle_btns.append(idx)
        if self.paddle_btns:
            print(f"[Controller] Paddles detected at buttons: {self.paddle_btns}")

        # center offsets (auto-calibrated)
        self.cx = self.cy = self.rx = self.ry = 0.0
        self._calibrate_centers()

        # previous outputs for rate limiting
        self.prev_surge = self.prev_sway = self.prev_heave = self.prev_yaw = 0

        # for debug printing
        self._last_buttons = 0
        self._last_button_names = []

    # ----- calibration -----
    def _calibrate_centers(self):
        print(f"[Controller] Calibrating centers for {CALIBRATION_SEC:.2f}s ...")
        t0 = time.time()
        xs = ys = x2 = y2 = 0.0
        rxs = rys = rx2 = ry2 = 0.0
        n = 0
        while time.time() - t0 < CALIBRATION_SEC:
            pygame.event.pump()
            lx = self.j.get_axis(self.AX_LX)
            ly = self.j.get_axis(self.AX_LY)
            rx = self.j.get_axis(self.AX_RX)
            ry = self.j.get_axis(self.AX_RY)
            xs += lx; ys += ly; x2 += lx*lx; y2 += ly*ly
            rxs += rx; rys += ry; rx2 += rx*rx; ry2 += ry*ry
            n += 1
            time.sleep(0.005)
        if n:
            self.cx = xs / n; self.cy = ys / n
            self.rx = rxs / n; self.ry = rys / n
        print(f"[Controller] Centers: LX={self.cx:.4f}, LY={self.cy:.4f}, RX={self.rx:.4f}, RY={self.ry:.4f}")

    # ----- input read + shaping -----
    def _read_axes_buttons(self):
        pygame.event.pump()

        # raw sticks minus centers
        lx = self.j.get_axis(self.AX_LX) - self.cx
        ly = self.j.get_axis(self.AX_LY) - self.cy
        rx = self.j.get_axis(self.AX_RX) - self.rx
        ry = self.j.get_axis(self.AX_RY) - self.ry

        # clamp
        lx = max(-1.0, min(1.0, lx))
        ly = max(-1.0, min(1.0, ly))
        rx = max(-1.0, min(1.0, rx))
        ry = max(-1.0, min(1.0, ry))

        # optional: radial deadzone (kept available if RADIAL_DZ>0)
        if RADIAL_DZ > 0.0:
            lx, ly = _radial_deadzone(lx, ly, RADIAL_DZ)
            rx, ry = _radial_deadzone(rx, ry, RADIAL_DZ)

        # strict per-axis deadzone: no output until |v| > AXIS_DZ, then rescale
        lx = _axis_deadzone(lx, AXIS_DZ)
        ly = _axis_deadzone(ly, AXIS_DZ)
        rx = _axis_deadzone(rx, AXIS_DZ)
        ry = _axis_deadzone(ry, AXIS_DZ)

        # anti-deadzone and expo
        lx = _expo(_apply_antidz(lx, ANTI_DZ), EXPO)
        ly = _expo(_apply_antidz(ly, ANTI_DZ), EXPO)
        rx = _expo(_apply_antidz(rx, ANTI_DZ), EXPO)
        ry = _expo(_apply_antidz(ry, ANTI_DZ), EXPO)

        # Map to vehicle axes (invert Y so up is +)
        surge = _axis_to_i16(-ly)  # forward/back (Left Y)
        sway  = _axis_to_i16(lx)   # left/right (Left X)
        yaw   = _axis_to_i16(rx)   # left/right (Right X)
        heave = _axis_to_i16(-ry)  # up/down   (Right Y)

        # Rate limit
        surge = _rate_limit(self.prev_surge, surge, MAX_DELTA_PER_T)
        sway  = _rate_limit(self.prev_sway,  sway,  MAX_DELTA_PER_T)
        heave = _rate_limit(self.prev_heave, heave, MAX_DELTA_PER_T)
        yaw   = _rate_limit(self.prev_yaw,   yaw,   MAX_DELTA_PER_T)
        self.prev_surge, self.prev_sway, self.prev_heave, self.prev_yaw = surge, sway, heave, yaw

        # ---------------- Buttons → bitfield ----------------
        def b(i): return 1 if (i < self.j.get_numbuttons() and self.j.get_button(i)) else 0
        bits = 0

        # Modes (B / Y / X) + SHIFT (A)
        if b(self.BTN_B): bits |= (1 << BIT["MODE_MANUAL"])
        if b(self.BTN_Y): bits |= (1 << BIT["MODE_DEPTH"])
        if b(self.BTN_X): bits |= (1 << BIT["MODE_STAB"])
        if b(self.BTN_A): bits |= (1 << BIT["SHIFT"])

        # Camera tilt RB/LB + center on L3
        if b(self.BTN_RB): bits |= (1 << BIT["CAM_TILT_UP"])
        if b(self.BTN_LB): bits |= (1 << BIT["CAM_TILT_DN"])
        if b(self.BTN_LS): bits |= (1 << BIT["CAM_TILT_CENTER"])

        # Arm/Disarm (Menu/View)
        if b(self.BTN_MENU): bits |= (1 << BIT["ARM"])
        if b(self.BTN_VIEW): bits |= (1 << BIT["DISARM"])

        # D-pad (hat 0) — gain/lights
        if self.j.get_numhats() > 0:
            hx, hy = self.j.get_hat(0)  # (-1,0,1)
            if hy > 0: bits |= (1 << BIT["GAIN_INC"])      # Up
            if hy < 0: bits |= (1 << BIT["GAIN_DEC"])      # Down
            if hx < 0: bits |= (1 << BIT["LIGHTS_DIM"])    # Left
            if hx > 0: bits |= (1 << BIT["LIGHTS_BRIGHT"]) # Right

        # Toggle Input Hold on R3
        if b(self.BTN_RS): bits |= (1 << BIT["TOGGLE_INPUT_HOLD"])

        # Optional: mirror paddles to useful actions
        for i, p in enumerate(self.paddle_btns):
            if b(p):
                if i == 0: bits |= (1 << BIT["CAM_TILT_UP"])
                elif i == 1: bits |= (1 << BIT["CAM_TILT_DN"])
                elif i == 2: bits |= (1 << BIT["ARM"])
                elif i == 3: bits |= (1 << BIT["DISARM"])

        # save for debug print
        self._last_buttons = bits
        self._last_button_names = self._collect_pressed_button_names(bits)

        armed = 1 if (bits & (1 << BIT["ARM"])) else 0
        return surge, sway, heave, yaw, bits, armed

    def _collect_pressed_button_names(self, bits: int):
        names = []
        def add(bit_name, label):
            if bits & (1 << BIT[bit_name]):
                names.append(label)

        add("MODE_MANUAL", "MANUAL(B)")
        add("MODE_DEPTH", "DEPTH(Y)")
        add("MODE_STAB", "STAB(X)")
        add("SHIFT", "SHIFT(A)")

        add("CAM_TILT_UP", "TILT_UP(RB)")
        add("CAM_TILT_DN", "TILT_DN(LB)")
        add("CAM_TILT_CENTER", "TILT_CENTER(L3)")

        add("GAIN_INC", "GAIN+ (DPAD↑)")
        add("GAIN_DEC", "GAIN- (DPAD↓)")
        add("LIGHTS_DIM", "LIGHTS- (DPAD←)")
        add("LIGHTS_BRIGHT", "LIGHTS+ (DPAD→)")

        add("TOGGLE_INPUT_HOLD", "INPUT_HOLD(R3)")
        add("ARM", "ARM(START)")
        add("DISARM", "DISARM(BACK)")
        return names

    # ----- main loop -----
    def run(self):
        period = 1.0 / max(1, RATE_HZ)
        print(f"[Controller] Streaming to {self.addr} @ {RATE_HZ} Hz")
        while True:
            surge, sway, heave, yaw, buttons, armed = self._read_axes_buttons()

            # DEBUG once per second
            if (self.seq % max(1, RATE_HZ)) == 0:
                print("surge/sway/heave/yaw:", surge, sway, heave, yaw,
                      " buttons:", bin(self._last_buttons),
                      " pressed:", self._last_button_names)

            pkt_wo_crc = struct.pack("!hhhhHBB", surge, sway, heave, yaw, buttons, armed, self.seq & 0xFF)
            pkt = pkt_wo_crc + struct.pack("!H", 0)  # CRC optional
            self.sock.sendto(pkt, self.addr)
            self.seq = (self.seq + 1) & 0xFF
            time.sleep(period)

# Quick CLI for testing
if __name__ == "__main__":
    Elite2ControllerSender().run()