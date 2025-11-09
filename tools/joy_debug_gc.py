import time, pygame
pygame.init()

# Prefer the new Controller API (pygame 2.5+)
try:
    pygame.controller.init()
    n = pygame.controller.get_count()
    print("Controllers:", n)
    ctrls = [pygame.controller.Controller(i) for i in range(n)]
    for c in ctrls:
        c.open()
        print("Name:", c.get_name(), "id:", c.get_id())
except Exception as e:
    print("Controller API failed:", e)
    n = 0

# Fallback to Joystick API (old)
pygame.joystick.init()
m = pygame.joystick.get_count()
sticks = [pygame.joystick.Joystick(i) for i in range(m)]
for s in sticks:
    s.init()
    print("Joystick:", s.get_name(), "axes:", s.get_numaxes(), "buttons:", s.get_numbuttons())

print("Move sticks / press buttons. Ctrl+C to quit.")
clock = pygame.time.Clock()
while True:
    for e in pygame.event.get():
        # GameController events (new API)
        if e.type == pygame.CONTROLLERAXISMOTION:
            print("[GC] axis", e.axis, "value", round(e.value,3), "which", e.instance_id)
        elif e.type == pygame.CONTROLLERBUTTONDOWN:
            print("[GC] button DOWN", e.button, "which", e.instance_id)
        elif e.type == pygame.CONTROLLERBUTTONUP:
            print("[GC] button UP  ", e.button, "which", e.instance_id)
        # Joystick events (old API)
        elif e.type == pygame.JOYAXISMOTION:
            print("[JS] axis", e.axis, "value", round(e.value,3), "joy", e.instance_id)
        elif e.type == pygame.JOYBUTTONDOWN:
            print("[JS] button DOWN", e.button, "joy", e.instance_id)
        elif e.type == pygame.JOYBUTTONUP:
            print("[JS] button UP  ", e.button, "joy", e.instance_id)
    clock.tick(120)
