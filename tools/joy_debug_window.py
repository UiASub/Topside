import pygame, time
pygame.init()
pygame.display.init()
pygame.display.set_mode((320, 120))  # tiny window to kick SDL
pygame.joystick.init()

if pygame.joystick.get_count()==0:
    raise SystemExit("No controllers")
j = pygame.joystick.Joystick(0); j.init()
print("Name:", j.get_name(), "axes:", j.get_numaxes(), "buttons:", j.get_numbuttons())
print("Move sticks / press buttons. Close window or Ctrl+C to quit.")

prev_axes = [None]*j.get_numaxes()
prev_btns = [None]*j.get_numbuttons()
clock = pygame.time.Clock()
running = True
while running:
    for e in pygame.event.get():
        if e.type == pygame.QUIT:
            running = False
    pygame.event.pump()
    axes = [round(j.get_axis(i), 3) for i in range(j.get_numaxes())]
    btns = [j.get_button(i) for i in range(j.get_numbuttons())]
    if axes != prev_axes or btns != prev_btns:
        print("axes", axes, "btns", btns)
        prev_axes, prev_btns = axes, btns
    clock.tick(120)
