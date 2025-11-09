import pygame
pygame.init()
pygame.display.init()
# Initialize joystick first to know counts for dynamic window sizing later
pygame.joystick.init()
if pygame.joystick.get_count()==0:
    raise SystemExit("No controllers")

j = pygame.joystick.Joystick(0); j.init()
name = j.get_name()
num_axes = j.get_numaxes()
num_btns = j.get_numbuttons()
num_hats = j.get_numhats()

# Dynamic window height based on number of inputs
line_height = 22
margin = 8
header_lines = 2
axis_section_height = num_axes * line_height
hat_section_height = (num_hats * line_height) if num_hats else 0
btn_section_height = ((num_btns + 15)//16) * line_height  # group buttons per row (16 per row)
height = margin*2 + (header_lines * line_height) + axis_section_height + hat_section_height + btn_section_height + 16
width = 560 if num_btns > 16 else 520
screen = pygame.display.set_mode((width, height))
pygame.display.set_caption(f"Joystick Debug: {name}")

font = pygame.font.SysFont("consolas", 16)
small_font = font

print("Name:", name, "axes:", num_axes, "buttons:", num_btns, "hats:", num_hats)
print("Beveg stikker / trykk knapper / D-pad. ESC eller lukk vindu for å avslutte.")

prev_axes = [None]*num_axes
prev_btns = [None]*num_btns
prev_hats = [None]*num_hats
clock = pygame.time.Clock()
running = True

BAR_W = 240
BAR_H = 12

while running:
    for e in pygame.event.get():
        if e.type == pygame.QUIT:
            running = False
        elif e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
            running = False
    pygame.event.pump()
    axes = [round(j.get_axis(i), 3) for i in range(num_axes)]
    btns = [j.get_button(i) for i in range(num_btns)]
    hats = [j.get_hat(i) for i in range(num_hats)] if num_hats else []

    # Only print to console on change
    if axes != prev_axes or btns != prev_btns or hats != prev_hats:
        print("axes", axes, "hats", hats, "btns", btns)
        prev_axes, prev_btns, prev_hats = axes, btns, hats

    # Draw background
    screen.fill((20, 20, 30))

    y = margin
    # Header
    header1 = font.render(f"Name: {name}", True, (200, 200, 220))
    header2 = font.render(f"Axes: {num_axes}  Buttons: {num_btns}  Hats: {num_hats}", True, (180, 180, 200))
    screen.blit(header1, (margin, y)); y += line_height
    screen.blit(header2, (margin, y)); y += line_height + 4

    # Axes section
    for i, val in enumerate(axes):
        # Axis label
        txt = font.render(f"Axis {i}: {val:+.3f}", True, (230, 230, 240))
        screen.blit(txt, (margin, y))
        # Bar background
        bar_x = 170
        center_x = bar_x + BAR_W // 2
        bar_rect = pygame.Rect(bar_x, y + (line_height-BAR_H)//2, BAR_W, BAR_H)
        pygame.draw.rect(screen, (60, 60, 80), bar_rect, border_radius=3)
        # Zero line
        pygame.draw.line(screen, (120, 120, 150), (center_x, bar_rect.top), (center_x, bar_rect.bottom))
        # Value indicator (value -1..1 mapped to -BAR_W/2..BAR_W/2)
        px = int(val * (BAR_W/2))
        if abs(px) < 2:  # show tiny for near zero
            px = 0
        color = (90, 200, 120) if abs(val) < 0.02 else (200, 180, 60) if abs(val) < 0.5 else (220, 80, 70)
        if px >= 0:
            val_rect = pygame.Rect(center_x, bar_rect.top, px, BAR_H)
        else:
            val_rect = pygame.Rect(center_x + px, bar_rect.top, -px, BAR_H)
        if val_rect.width>0:
            pygame.draw.rect(screen, color, val_rect, border_radius=3)
        y += line_height

    # Hats (D-pad) section
    if num_hats:
        y += 2
        for i, (hx, hy) in enumerate(hats):
            # Draw a small 3x3 grid with highlighted direction
            txt = font.render(f"Hat {i}: ({hx:+d},{hy:+d})", True, (220, 220, 235))
            screen.blit(txt, (margin, y))
            cell = 18
            gx = 200
            gy = y + 2
            # Background grid
            for cy in range(3):
                for cx in range(3):
                    rect = pygame.Rect(gx + cx*cell, gy + cy*cell, cell-2, cell-2)
                    pygame.draw.rect(screen, (55,55,70), rect, border_radius=4)
            # Active cell (map -1,0,1 to 0,1,2 index)
            ax = hx + 1
            ay = (-hy) + 1  # invert y (up is -1)
            if 0 <= ax < 3 and 0 <= ay < 3:
                rect = pygame.Rect(gx + ax*cell, gy + ay*cell, cell-2, cell-2)
                pygame.draw.rect(screen, (40,180,120), rect, border_radius=4)
            y += line_height
        y += 2

    # Buttons grouped 16 per row
    btns_per_row = 16
    rows = (num_btns + btns_per_row - 1)//btns_per_row
    for r in range(rows):
        row_btns = range(r*btns_per_row, min(num_btns, (r+1)*btns_per_row))
        x = margin
        for i in row_btns:
            pressed = btns[i]
            rect = pygame.Rect(x, y, 30, 22)
            pygame.draw.rect(screen, (70, 70, 90), rect, border_radius=4)
            if pressed:
                pygame.draw.rect(screen, (40, 180, 80), rect, border_radius=4)
            # Button index text
            t = small_font.render(str(i), True, (240, 240, 255))
            tw, th = t.get_size()
            screen.blit(t, (x + (30 - tw)//2, y + (22 - th)//2))
            x += 34
        y += line_height

    # FPS (optional)
    fps = clock.get_fps()
    fps_txt = small_font.render(f"FPS: {fps:4.0f}", True, (160, 160, 180))
    screen.blit(fps_txt, (width - 90, height - 24))

    pygame.display.flip()
    clock.tick(120)

pygame.quit()
