let controllerIndex = null;
let backendCommand = null;
let backendButtons = null;
let backendCommandTime = 0;
let backendPollTimer = null;

const RAW_COMMAND_SCALE = 127;

function findConnectedGamepad() {
  const gamepads = navigator.getGamepads ? navigator.getGamepads() : [];
  for (const gamepad of gamepads) {
    if (gamepad && gamepad.connected) {
      return gamepad;
    }
  }
  return null;
}

window.addEventListener("gamepadconnected", (event) => {
  const gamepad = event.gamepad;
  console.log("Gamepad connected:", gamepad.id);
  controllerIndex = gamepad.index;
});

window.addEventListener("gamepaddisconnected", (event) => {
  console.log("Gamepad disconnected:", event.gamepad.id);
  controllerIndex = null;
  // Reset all buttons when disconnected
  resetController();
});

function resetController() {
  // Reset all buttons
  for (let i = 0; i <= 15; i++) {
    const button = document.getElementById(`controller-b${i}`);
    if (button) {
      button.classList.remove("selected-button");
    }
  }
  // Reset joysticks
  resetStick("controller-b10");
  resetStick("controller-b11");
}

function getBackendAxis(command, axis) {
  return Math.max(-1, Math.min(1, (command[axis] || 0) / RAW_COMMAND_SCALE));
}

function updateControllerFromCommand(command) {
  resetController();

  const surge = getBackendAxis(command, "surge");
  const sway = getBackendAxis(command, "sway");
  const heave = getBackendAxis(command, "heave");
  const roll = getBackendAxis(command, "roll");
  const pitch = getBackendAxis(command, "pitch");
  const yaw = getBackendAxis(command, "yaw");

  if (Math.abs(pitch) > 0.01 || Math.abs(roll) > 0.01) {
    updateControllerButton(4, 1);
    updateStick("controller-b10", roll, -pitch);
  } else {
    updateStick("controller-b10", sway, -surge);
  }

  updateStick("controller-b11", yaw, -heave);

  if (backendButtons) {
    updateControllerButtonsFromValues(backendButtons);
  }
}

function commandIsActive(command) {
  return ["surge", "sway", "heave", "roll", "pitch", "yaw"].some((axis) => Math.abs(command[axis] || 0) > 1);
}

async function fetchBackendCommand() {
  try {
    const response = await fetch("/api/command/status", { cache: "no-store" });
    if (!response.ok) return;

    const data = await response.json();
    const command = data && data.uplink && data.uplink.last_command;
    const buttons = data && data.controller && data.controller.buttons;
    if (command) {
      backendCommand = command;
      backendButtons = Array.isArray(buttons) ? buttons : null;
      backendCommandTime = performance.now();
    }
  } catch (error) {
    console.debug("Controller command status unavailable:", error);
  }
}

function resetStick(elementId) {
  const stick = document.getElementById(elementId);
  if (!stick) return;
  
  const x = Number(stick.dataset.originalXPosition);
  const y = Number(stick.dataset.originalYPosition);
  
  stick.setAttribute("cx", x);
  stick.setAttribute("cy", y);
  stick.classList.remove("stick-active");
}

function updateControllerButton(index, value) {
  const button = document.getElementById(`controller-b${index}`);
  const selectedButtonClass = "selected-button";
  
  if (button) {
    if (value > 0.1) {
      button.classList.add(selectedButtonClass);
    } else {
      button.classList.remove(selectedButtonClass);
    }
  }
}

function handleButtons(buttons) {
  updateControllerButtonsFromValues(buttons);
}

function updateControllerButtonsFromValues(buttons) {
  for (let i = 0; i < buttons.length; i++) {
    const button = buttons[i];
    const buttonValue = typeof button === "number" ? button : button.value;
    updateControllerButton(i, buttonValue);
  }
}

function handleSticks(axes) {
  updateStick("controller-b10", axes[0] || 0, axes[1] || 0);
  updateStick("controller-b11", axes[2] || 0, axes[3] || 0);
}

function updateStick(elementId, leftRightAxis, upDownAxis) {
  const multiplier = 25;
  const stickLeftRight = leftRightAxis * multiplier;
  const stickUpDown = upDownAxis * multiplier;

  const stick = document.getElementById(elementId);
  if (!stick) return;
  
  const x = Number(stick.dataset.originalXPosition);
  const y = Number(stick.dataset.originalYPosition);

  stick.setAttribute("cx", x + stickLeftRight);
  stick.setAttribute("cy", y + stickUpDown);
  
  // Add active class when stick is moved beyond deadzone
  const deadzone = 0.1;
  if (Math.abs(leftRightAxis) > deadzone || Math.abs(upDownAxis) > deadzone) {
    stick.classList.add("stick-active");
  } else {
    stick.classList.remove("stick-active");
  }
}

function gameLoop() {
  let gamepad = null;

  if (controllerIndex !== null && navigator.getGamepads) {
    gamepad = navigator.getGamepads()[controllerIndex];
  }

  if (!gamepad) {
    gamepad = findConnectedGamepad();
    controllerIndex = gamepad ? gamepad.index : null;
  }

  if (backendCommand && performance.now() - backendCommandTime < 1000 && (!gamepad || commandIsActive(backendCommand))) {
    updateControllerFromCommand(backendCommand);
  } else if (gamepad) {
    handleButtons(gamepad.buttons);
    handleSticks(gamepad.axes);
  } else {
    resetController();
  }

  requestAnimationFrame(gameLoop);
}

backendPollTimer = setInterval(fetchBackendCommand, 100);
fetchBackendCommand();
gameLoop();

window.addEventListener("beforeunload", () => {
  if (backendPollTimer) {
    clearInterval(backendPollTimer);
  }
});
