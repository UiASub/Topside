# tools/joy_calibrate_axes_v2.py
import time, pygame
pygame.init(); pygame.joystick.init()
if pygame.joystick.get_count()==0: raise SystemExit("No controllers")
j = pygame.joystick.Joystick(0); j.init()
print("Controller:", j.get_name(), "axes:", j.get_numaxes())
used=set()

def detect(prompt, forbid=set()):
    print(prompt, "(keep ONLY that stick moving)")
    base=[j.get_axis(i) for i in range(j.get_numaxes())]
    best_i=-1; best_d=0.0
    t0=time.time()
    while time.time()-t0<3.0:
        pygame.event.pump()
        vals=[j.get_axis(i) for i in range(j.get_numaxes())]
        for i,v in enumerate(vals):
            if i in forbid or i in used:
                continue
            d=abs(v-base[i])
            if d>best_d:
                best_d=d; best_i=i
        time.sleep(0.01)
    print(" -> Axis", best_i, "diff", round(best_d,3))
    used.add(best_i); time.sleep(0.5)
    return best_i

# assume triggers are usually 4,5 – forbid them by default
TRIG_GUESS={4,5}
lx=detect("Move LEFT STICK horizontally", TRIG_GUESS)
ly=detect("Move LEFT STICK vertically", TRIG_GUESS)
rx=detect("Move RIGHT STICK horizontally", TRIG_GUESS|{lx,ly})
ry=detect("Move RIGHT STICK vertically", TRIG_GUESS|{lx,ly,rx})
print(f"\nDetected: AX_LX={lx}, AX_LY={ly}, AX_RX={rx}, AX_RY={ry}")
