import pygame

class PS4Kontroller:
    AXIS_THRESHOLDS = {
        "leftx":  (0, 0.08),
        "lefty":  (1, 0.08),
        "rightx": (2, 0.08),
        "righty": (3, 0.08)
    }

    def __init__(self):
        pygame.init()
        pygame.joystick.init()
        self.joystick = None
        self.connect_joystick()

    def connect_joystick(self):
        if pygame.joystick.get_count() > 0:
            self.joystick = pygame.joystick.Joystick(0)
            self.joystick.init()
            print("PS4 Controller connected.")
        else:
            print("No PS4 Controller found.")

    def update(self):
        pygame.event.pump()

        if not self.joystick:
            return

        # ---- PRINT ALLE KNAPPER ----
        for i in range(self.joystick.get_numbuttons()):
            state = self.joystick.get_button(i)
            if state:
                print(f"Button {i} pressed")

        # ---- PRINT AKSER KUN HVIS DE PASSERER TERSKEL ----
        for name, (axis_id, threshold) in self.AXIS_THRESHOLDS.items():
            value = self.joystick.get_axis(axis_id)
            if abs(value) > abs(threshold):
                print(f"{name}: {value:.3f}")
            else:
                print(f"{name}: 0.000")

controller = PS4Kontroller()
while True:
    controller.update()
    pygame.time.delay(100)