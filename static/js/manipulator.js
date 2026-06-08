// Shared manipulator controls for Home and Pilot views.

let _manipPostTimer = null;
let _manipActiveSlider = null;

const MANIP_SLIDER_IDS = ["manipulator-slider", "hud-manipulator-slider"];

function manipFmt(value) {
  return typeof value === "number" && Number.isFinite(value) ? `${value.toFixed(0)} deg` : "--";
}

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

function updateManipulatorDisplays(data) {
  const target = Number(data.target_deg ?? data.setpoint_deg ?? 0);
  const applied = typeof data.applied_deg === "number" ? data.applied_deg : null;
  const pulse = typeof data.pulse_us === "number" ? data.pulse_us : null;

  setText("manipulator-target-value", target.toFixed(0));
  setText("manipulator-applied-value", applied == null ? "--" : applied.toFixed(1));
  setText("manipulator-pulse-value", pulse == null ? "--" : String(pulse));
  setText("manipulator-source-value", data.source || "--");

  setText("hud-manipulator-target", manipFmt(target));
  setText("hud-manipulator-applied", applied == null ? "--" : `${applied.toFixed(1)} deg`);
  setText("hud-manipulator-pulse", pulse == null ? "--" : `${pulse} us`);

  MANIP_SLIDER_IDS.forEach((id) => {
    const slider = document.getElementById(id);
    if (slider && slider !== _manipActiveSlider) {
      slider.value = target.toFixed(0);
    }
  });
}

async function fetchManipulator() {
  try {
    const res = await fetch("/api/manipulator", { cache: "no-store" });
    const data = await res.json();
    if (data && data.ok) updateManipulatorDisplays(data);
  } catch (error) {
    console.error("Error fetching manipulator:", error);
  }
}

async function postManipulator(setpointDeg) {
  try {
    const res = await fetch("/api/manipulator", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ setpoint_deg: setpointDeg }),
    });
    const data = await res.json();
    if (data && data.ok) updateManipulatorDisplays(data);
  } catch (error) {
    console.error("Error setting manipulator:", error);
  }
}

function queueManipulatorPost(value) {
  if (_manipPostTimer) return;
  _manipPostTimer = setTimeout(() => {
    _manipPostTimer = null;
  }, 100);
  postManipulator(value);
}

function bindManipulatorSlider(id) {
  const slider = document.getElementById(id);
  if (!slider) return;

  slider.addEventListener("pointerdown", () => {
    _manipActiveSlider = slider;
  });
  slider.addEventListener("input", () => {
    _manipActiveSlider = slider;
    const value = parseFloat(slider.value) || 0;
    setText("manipulator-target-value", value.toFixed(0));
    setText("hud-manipulator-target", manipFmt(value));
    queueManipulatorPost(value);
  });
  slider.addEventListener("pointerup", () => {
    const value = parseFloat(slider.value) || 0;
    postManipulator(value);
    _manipActiveSlider = null;
  });
  slider.addEventListener("pointercancel", () => {
    _manipActiveSlider = null;
  });
  slider.addEventListener("change", () => {
    const value = parseFloat(slider.value) || 0;
    postManipulator(value);
    _manipActiveSlider = null;
  });
  slider.addEventListener("blur", () => {
    _manipActiveSlider = null;
  });
}

document.addEventListener("DOMContentLoaded", () => {
  MANIP_SLIDER_IDS.forEach(bindManipulatorSlider);
  fetchManipulator();
  setInterval(fetchManipulator, 250);
});
