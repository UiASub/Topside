import time, pygame
pygame.init(); pygame.joystick.init()
if pygame.joystick.get_count()==0: raise SystemExit("No controllers")
j = pygame.joystick.Joystick(0); j.init()
print("Name:", j.get_name(), "axes:", j.get_numaxes(), "buttons:", j.get_numbuttons())
print("Move sticks / press buttons. Ctrl+C to quit.")
prev_axes = [None]*j.get_numaxes()
prev_btns = [None]*j.get_numbuttons()
while True:
    pygame.event.pump()
    axes = [round(j.get_axis(i), 3) for i in range(j.get_numaxes())]
    btns = [j.get_button(i) for i in range(j.get_numbuttons())]
    if axes != prev_axes or btns != prev_btns:
        print("axes", axes, "btns", btns)
        prev_axes, prev_btns = axes, btns
    time.sleep(0.02)
