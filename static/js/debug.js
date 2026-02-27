// debug.js – Debug slider page logic
(function () {
  const AXES = ["surge", "sway", "heave", "roll", "pitch", "yaw"];
  const SEND_INTERVAL_MS = 50; // 20 Hz updates while override is active

  let overrideActive = false;
  let sendTimer = null;

  // DOM refs
  const btnEnable = document.getElementById("btn-enable");
  const btnDisable = document.getElementById("btn-disable");
  const btnResetAll = document.getElementById("btn-reset-all");
  const statusBadge = document.getElementById("debug-status");
  const rovStatus = document.getElementById("rov-status");

  // --- Slider helpers ---
  function getSliderValue(axis) {
    return parseInt(document.getElementById("slider-" + axis).value, 10) / 100;
  }

  function getAllValues() {
    const vals = {};
    AXES.forEach((a) => (vals[a] = getSliderValue(a)));
    return vals;
  }

  function updateValueDisplay(axis) {
    const val = getSliderValue(axis);
    const el = document.getElementById("val-" + axis);
    el.textContent = val.toFixed(2);

    // colour class
    const slider = document.getElementById("slider-" + axis);
    slider.classList.remove("positive", "negative", "zero");
    if (val > 0.005) slider.classList.add("positive");
    else if (val < -0.005) slider.classList.add("negative");
    else slider.classList.add("zero");
  }

  function resetSlider(axis) {
    document.getElementById("slider-" + axis).value = 0;
    updateValueDisplay(axis);
  }

  // --- API calls ---
  async function sendOverride() {
    if (!overrideActive) return;
    try {
      await fetch("/api/debug/override", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(getAllValues()),
      });
    } catch (e) {
      console.error("Failed to send debug override:", e);
    }
  }

  async function clearOverride() {
    try {
      await fetch("/api/debug/clear", { method: "POST" });
    } catch (e) {
      console.error("Failed to clear debug override:", e);
    }
  }

  async function pollStatus() {
    try {
      const res = await fetch("/api/rov/status");
      const data = await res.json();
      rovStatus.textContent = JSON.stringify(data.command, null, 2);
    } catch (_) {
      rovStatus.textContent = "Error fetching status";
    }
  }

  // --- Enable / Disable ---
  function enableOverride() {
    overrideActive = true;
    btnEnable.disabled = true;
    btnDisable.disabled = false;
    statusBadge.textContent = "ACTIVE";
    statusBadge.classList.remove("bg-secondary");
    statusBadge.classList.add("bg-danger", "active");

    // Start sending slider values at 20 Hz
    sendOverride(); // send immediately
    sendTimer = setInterval(sendOverride, SEND_INTERVAL_MS);
  }

  function disableOverride() {
    overrideActive = false;
    btnEnable.disabled = false;
    btnDisable.disabled = true;
    statusBadge.textContent = "INACTIVE";
    statusBadge.classList.remove("bg-danger", "active");
    statusBadge.classList.add("bg-secondary");

    if (sendTimer) {
      clearInterval(sendTimer);
      sendTimer = null;
    }
    clearOverride();
  }

  // --- Event wiring ---
  btnEnable.addEventListener("click", enableOverride);
  btnDisable.addEventListener("click", disableOverride);
  btnResetAll.addEventListener("click", () => AXES.forEach(resetSlider));

  AXES.forEach((axis) => {
    const slider = document.getElementById("slider-" + axis);
    slider.addEventListener("input", () => updateValueDisplay(axis));
    slider.addEventListener("dblclick", () => resetSlider(axis));
    updateValueDisplay(axis); // init
  });

  // Poll ROV status every 500 ms
  pollStatus();
  setInterval(pollStatus, 500);
})();
