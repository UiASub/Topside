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

# Deadzone tuning (Elite 2 with drift: increase RADIAL_DZ slightly if needed)
RADIAL_DZ       = float(os.getenv("RADIAL_DZ", "0.14"))  # 0..0.3 typical
ANTI_DZ         = float(os.getenv("ANTI_DZ", "0.06"))    # pushes small input past DZ
EXPO            = float(os.getenv("EXPO", "0.25"))       # 0 = linear, 0.2-0.4 nice
MAX_DELTA_PER_T = int(os.getenv("MAX_DELTA_PER_T", "120"))  # rate limit per tick (int16 units)

# Startup center calibration
CALIBRATION_SEC = float(os.getenv("CALIBRATION_SEC", "0.8"))

# Buttons bitfield layout
BIT = {
    "MODE_MANUAL": 0,
    "MODE_DEPTH":  1,
    "MODE_STAB":   2,
    "CAM_TILT_UP": 3,
    "CAM_TILT_DN": 4,
    "ARM":        14,
    "DISARM":     15,
}

# ===================== Helpers =====================

def _axis_to_i16(v: float) -> int:
    v = max(-1.0, min(1.0, v))
    return int(round(v * 1000))

def _expo(v: float, e: float) -> float:
    # Smooth around center while keeping end range
    if e <= 1e-6: return v
    return math.copysign(abs(v) ** (1.0 + e), v)

def _radial_deadzone(x: float, y: float, dz: float):
    r = math.sqrt(x*x + y*y)
    if r < dz:
        return 0.0, 0.0
    # scale remaining radius back to 0..1
    scale = (r - dz) / (1.0 - dz)
    if r > 1e-6:
        x = (x / r) * scale
        y = (y / r) * scale
    return x, y

def _apply_antidz(v: float, adz: float) -> float:
    if v == 0.0: return 0.0
    # nudge small values past the sticky region
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
    Reads an Xbox Elite/Series controller via pygame (SDL), applies drift mitigation,
    and streams binary UDP packets to the ROV at RATE_HZ.
    """

    def __init__(self, ip=UDP_IP, port=UDP_PORT):
        self.addr = (ip, port)
        self.seq  = 0
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        pygame.init()
        pygame.joystick.init()

        if pygame.joystick.get_count() == 0:
            raise RuntimeError("No controller detected")

        # Pick first controller; prefer Xbox/Elite if present (covers BT "Series X Controller" too)
        chosen = 0
        for i in range(pygame.joystick.get_count()):
            name = pygame.joystick.Joystick(i).get_name().lower()
            if "elite" in name or "xbox" in name or "microsoft" in name or "series" in name:
                chosen = i
                break

        self.j = pygame.joystick.Joystick(chosen)
        self.j.init()
        self.name = self.j.get_name()
        print(f"[Controller] Connected: {self.name} (axes={self.j.get_numaxes()}, buttons={self.j.get_numbuttons()})")

        # ---- Axis indices (macOS mapping: 0=LX,1=LY,2=RX,3=RY; triggers typically 4,5) ----
        self.AX_LX, self.AX_LY, self.AX_RX, self.AX_RY = 0, 1, 2, 3

        # ---- Button indices (SDL on macOS) ----
        # A=0, B=1, X=2, Y=3, LB=4, RB=5, View/Back=8, Menu/Start=9, LS=10, RS=11
        self.BTN_A, self.BTN_B, self.BTN_X, self.BTN_Y = 0, 1, 2, 3
        self.BTN_LB, self.BTN_RB = 4, 5
        self.BTN_VIEW, self.BTN_MENU = 8, 9
        self.BTN_LS, self.BTN_RS = 10, 11

        # Elite/Series paddles often appear around 12..15 on macOS (adjust after checking joy_debug.py)
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

        # radial deadzone on both sticks
        lx, ly = _radial_deadzone(lx, ly, RADIAL_DZ)
        rx, ry = _radial_deadzone(rx, ry, RADIAL_DZ)

        # anti-deadzone and expo
        lx = _expo(_apply_antidz(lx, ANTI_DZ), EXPO)
        ly = _expo(_apply_antidz(ly, ANTI_DZ), EXPO)
        rx = _expo(_apply_antidz(rx, ANTI_DZ), EXPO)
        ry = _expo(_apply_antidz(ry, ANTI_DZ), EXPO)

        # Map to vehicle axes (note Y inverted so up is positive)
        surge = _axis_to_i16(-ly)  # forward/back
        sway  = _axis_to_i16(lx)   # left/right
        yaw   = _axis_to_i16(rx)   # turn
        heave = _axis_to_i16(-ry)  # up/down

        # Rate limit (optional but feels better)
        surge = _rate_limit(self.prev_surge, surge, MAX_DELTA_PER_T)
        sway  = _rate_limit(self.prev_sway,  sway,  MAX_DELTA_PER_T)
        heave = _rate_limit(self.prev_heave, heave, MAX_DELTA_PER_T)
        yaw   = _rate_limit(self.prev_yaw,   yaw,   MAX_DELTA_PER_T)
        self.prev_surge, self.prev_sway, self.prev_heave, self.prev_yaw = surge, sway, heave, yaw

        # Buttons → bitfield
        def b(i): return 1 if (i < self.j.get_numbuttons() and self.j.get_button(i)) else 0
        bits = 0
        if b(self.BTN_B): bits |= (1 << BIT["MODE_MANUAL"])
        if b(self.BTN_A): bits |= (1 << BIT["MODE_DEPTH"])
        if b(self.BTN_X): bits |= (1 << BIT["MODE_STAB"])
        if b(self.BTN_RB): bits |= (1 << BIT["CAM_TILT_UP"])
        if b(self.BTN_LB): bits |= (1 << BIT["CAM_TILT_DN"])
        if b(self.BTN_MENU):  bits |= (1 << BIT["ARM"])
        if b(self.BTN_VIEW):  bits |= (1 << BIT["DISARM"])

        # Optional: map paddles as duplicates (e.g., P1/P2 camera, P3 arm, P4 disarm)
        if self.paddle_btns:
            if b(self.paddle_btns[0]): bits |= (1 << BIT["CAM_TILT_UP"])
            if len(self.paddle_btns) > 1 and b(self.paddle_btns[1]): bits |= (1 << BIT["CAM_TILT_DN"])
            if len(self.paddle_btns) > 2 and b(self.paddle_btns[2]): bits |= (1 << BIT["ARM"])
            if len(self.paddle_btns) > 3 and b(self.paddle_btns[3]): bits |= (1 << BIT["DISARM"])

        armed = 1 if (bits & (1 << BIT["ARM"])) else 0
        return surge, sway, heave, yaw, bits, armed

    # ----- main loop -----
    def run(self):
        period = 1.0 / max(1, RATE_HZ)
        print(f"[Controller] Streaming to {self.addr} @ {RATE_HZ} Hz")
        while True:
            surge, sway, heave, yaw, buttons, armed = self._read_axes_buttons()

            # DEBUG: print once per second (helpful during setup; remove later)
            if (self.seq % max(1, RATE_HZ)) == 0:
                print("surge/sway/heave/yaw:", surge, sway, heave, yaw)

            pkt_wo_crc = struct.pack("!hhhhHBB", surge, sway, heave, yaw, buttons, armed, self.seq & 0xFF)
            crc = 0  # (optional) fill with CRC16 if you enable it in firmware
            pkt = pkt_wo_crc + struct.pack("!H", crc)
            self.sock.sendto(pkt, self.addr)
            self.seq = (self.seq + 1) & 0xFF
            time.sleep(period)

# Quick CLI for testing
if __name__ == "__main__":
    Elite2ControllerSender().run()
