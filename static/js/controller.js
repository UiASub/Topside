let controllerIndex = null;

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
  for (let i = 0; i < buttons.length; i++) {
    const buttonValue = buttons[i].value;
    updateControllerButton(i, buttonValue);
  }
}

function handleSticks(axes) {
  updateStick("controller-b10", axes[0], axes[1]);
  updateStick("controller-b11", axes[2], axes[3]);
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
  if (controllerIndex !== null) {
    const gamepad = navigator.getGamepads()[controllerIndex];
    if (gamepad) {
      handleButtons(gamepad.buttons);
      handleSticks(gamepad.axes);
    }
  }
  requestAnimationFrame(gameLoop);
}

gameLoop();