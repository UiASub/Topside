# confirm your exact button/axis confirms check

import pygame, time
pygame.init(); pygame.joystick.init()
if pygame.joystick.get_count()==0: raise SystemExit("No controllers")
j = pygame.joystick.Joystick(0); j.init()
print("Name:", j.get_name(), "axes:", j.get_numaxes(), "buttons:", j.get_numbuttons())
print("Press Ctrl+C to exit...")

try:
    while True:
        pygame.event.pump()
        axes = [round(j.get_axis(i),4) for i in range(j.get_numaxes())]
        btns = [j.get_button(i) for i in range(j.get_numbuttons())]
        print("axes", axes, "btns", btns)
        time.sleep(0.2)
except KeyboardInterrupt:
    print("\nExiting gracefully...")
    pygame.quit()
