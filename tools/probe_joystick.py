"""Live joystick probe.

Prints every axis, button, and hat your controller exposes, with their
indices, so you can build a mapping for lib/controller.py. Works with any
pygame-detected device (flight stick, gamepad, wheel, farm panel, etc.).

It first captures a RESTING BASELINE for every axis, then reports movement
relative to that baseline. This matters for lever/throttle/trigger axes that
rest at -1.0 (one extreme) instead of 0.0 (center) -- without a baseline they
look "always active."

Run it, then move each control one at a time and watch which index changes:

    uv run python tools/probe_joystick.py
    # or, without uv:
    python tools/probe_joystick.py

Press Ctrl+C to quit.
"""

import os
import time

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

import pygame

# How far an axis must move from its resting baseline before we report it.
# Raise this if a jittery axis spams; lower it to catch small movements.
MOVE_THRESHOLD = 0.15
REFRESH_HZ = 30
BASELINE_SETTLE_SEC = 0.5


def pick_joystick():
    pygame.init()
    pygame.joystick.init()

    count = pygame.joystick.get_count()
    if count == 0:
        print("No joystick detected. Plug it in and try again.")
        return None

    sticks = []
    for index in range(count):
        js = pygame.joystick.Joystick(index)
        js.init()
        sticks.append(js)
        print(f"[{index}] {js.get_name()}  "
              f"(axes={js.get_numaxes()}, buttons={js.get_numbuttons()}, hats={js.get_numhats()})")

    if count == 1:
        return sticks[0]

    while True:
        choice = input(f"Select joystick index [0-{count - 1}]: ").strip()
        if choice.isdigit() and int(choice) < count:
            return sticks[int(choice)]
        print("Invalid selection.")


def capture_baseline(js, num_axes):
    """Read resting axis values so we can report movement relative to them."""
    deadline = time.time() + BASELINE_SETTLE_SEC
    baseline = [0.0] * num_axes
    while time.time() < deadline:
        pygame.event.pump()
        for a in range(num_axes):
            baseline[a] = js.get_axis(a)
        time.sleep(1.0 / REFRESH_HZ)
    return baseline


def main():
    js = pick_joystick()
    if js is None:
        return

    num_axes = js.get_numaxes()
    num_buttons = js.get_numbuttons()
    num_hats = js.get_numhats()

    print()
    print(f"Probing: {js.get_name()}")
    print(f"  axes={num_axes}  buttons={num_buttons}  hats={num_hats}")
    print()
    print("Calibrating resting baseline -- do NOT touch the controls...")
    baseline = capture_baseline(js, num_axes)
    print("Resting axis values: " + ", ".join(f"a{a}={baseline[a]:+.2f}" for a in range(num_axes)))
    print()
    print("Move ONE control at a time and note its index. Ctrl+C to quit.")
    print("(axis values shown as deviation from resting baseline)")
    print("-" * 60)

    try:
        while True:
            pygame.event.pump()

            active = []

            for a in range(num_axes):
                delta = js.get_axis(a) - baseline[a]
                if abs(delta) > MOVE_THRESHOLD:
                    active.append(f"axis {a}: {delta:+.2f}")

            for b in range(num_buttons):
                if js.get_button(b):
                    active.append(f"button {b}: PRESSED")

            for h in range(num_hats):
                hat = js.get_hat(h)
                if hat != (0, 0):
                    active.append(f"hat {h}: {hat}")

            if active:
                print("  " + " | ".join(active))

            time.sleep(1.0 / REFRESH_HZ)
    except KeyboardInterrupt:
        print("\nDone.")
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()
