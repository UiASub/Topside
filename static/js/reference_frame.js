(function () {
  "use strict";

  let currentFrame = "rov";

  function updateFrameUi(frame) {
    currentFrame = frame === "global" ? "global" : "rov";
    document.querySelectorAll(".reference-frame-btn").forEach((button) => {
      button.classList.toggle("is-active", button.dataset.frame === currentFrame);
    });

    const status = document.getElementById("reference-frame-status");
    if (status) {
      status.textContent = currentFrame === "global" ? "Global frame active" : "ROV frame active";
    }
  }

  async function fetchFrame() {
    try {
      const response = await fetch("/api/rov/reference_frame");
      const data = await response.json();
      if (data.ok) updateFrameUi(data.reference_frame);
    } catch (_) {
      const status = document.getElementById("reference-frame-status");
      if (status) status.textContent = "Frame status unavailable";
    }
  }

  async function setFrame(frame) {
    const nextFrame = frame === "global" ? "global" : "rov";
    const previousFrame = currentFrame;
    updateFrameUi(nextFrame);

    try {
      const response = await fetch("/api/rov/reference_frame", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reference_frame: nextFrame }),
      });
      const data = await response.json();
      if (data.ok) {
        updateFrameUi(data.reference_frame);
      } else {
        updateFrameUi(previousFrame);
      }
    } catch (_) {
      updateFrameUi(previousFrame);
    }
  }

  function initReferenceFrameToggle() {
    const buttons = document.querySelectorAll(".reference-frame-btn");
    if (!buttons.length) return;

    buttons.forEach((button) => {
      button.addEventListener("click", () => setFrame(button.dataset.frame));
    });

    fetchFrame();
    setInterval(fetchFrame, 3000);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initReferenceFrameToggle);
  } else {
    initReferenceFrameToggle();
  }
})();
