(function () {
  const AXES = ["surge", "sway", "heave", "roll", "pitch", "yaw"];
  const SEND_INTERVAL_MS = 50;

  let overrideActive = false;
  let sendTimer = null;

  const btnEnable = document.getElementById("btn-enable");
  const btnDisable = document.getElementById("btn-disable");
  const btnResetAll = document.getElementById("btn-reset-all");
  const btnStopAll = document.getElementById("btn-stop-all");
  const statusBadge = document.getElementById("debug-status");
  const rovStatus = document.getElementById("rov-status");

  function slider(axis) {
    return document.getElementById("slider-" + axis);
  }

  function getSliderValue(axis) {
    const el = slider(axis);
    return el ? parseInt(el.value, 10) / 100 : 0;
  }

  function getAllValues() {
    const values = {};
    AXES.forEach((axis) => {
      values[axis] = getSliderValue(axis);
    });
    return values;
  }

  function updateValueDisplay(axis) {
    const value = getSliderValue(axis);
    const valueEl = document.getElementById("val-" + axis);
    const sliderEl = slider(axis);
    if (valueEl) valueEl.textContent = value.toFixed(2);
    if (!sliderEl) return;
    sliderEl.classList.remove("positive", "negative", "zero");
    if (value > 0.005) sliderEl.classList.add("positive");
    else if (value < -0.005) sliderEl.classList.add("negative");
    else sliderEl.classList.add("zero");
  }

  function resetSlider(axis) {
    const el = slider(axis);
    if (!el) return;
    el.value = 0;
    updateValueDisplay(axis);
  }

  function setOverrideUi(active) {
    overrideActive = active;
    if (btnEnable) btnEnable.disabled = active;
    if (btnDisable) btnDisable.disabled = !active;
    if (statusBadge) {
      statusBadge.textContent = active ? "ACTIVE" : "INACTIVE";
      statusBadge.className = "badge " + (active ? "bg-danger" : "bg-secondary");
    }
    if (!active && sendTimer) {
      clearInterval(sendTimer);
      sendTimer = null;
    }
  }

  async function sendOverride() {
    if (!overrideActive) return;
    try {
      await fetch("/api/debug/override", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(getAllValues()),
      });
    } catch (error) {
      console.error("Failed to send debug override:", error);
    }
  }

  async function clearOverride() {
    try {
      const res = await fetch("/api/debug/clear", { method: "POST" });
      return res.ok;
    } catch (error) {
      console.error("Failed to clear debug override:", error);
      return false;
    }
  }

  function enableOverride() {
    setOverrideUi(true);
    sendOverride();
    sendTimer = setInterval(sendOverride, SEND_INTERVAL_MS);
  }

  async function stopAll() {
    setOverrideUi(false);
    AXES.forEach(resetSlider);
    await clearOverride();
    pollStatus();
  }

  async function pollStatus() {
    if (!rovStatus) return;
    try {
      const res = await fetch("/api/rov/status", { cache: "no-store" });
      const data = await res.json();
      rovStatus.textContent = JSON.stringify(
        {
          command: data.command,
          uplink: data.uplink,
          resource: data.resource,
        },
        null,
        2
      );
    } catch (_) {
      rovStatus.textContent = "Error fetching status";
    }
  }

  if (btnEnable) btnEnable.addEventListener("click", enableOverride);
  if (btnDisable) btnDisable.addEventListener("click", stopAll);
  if (btnResetAll) btnResetAll.addEventListener("click", () => AXES.forEach(resetSlider));
  if (btnStopAll) btnStopAll.addEventListener("click", stopAll);

  AXES.forEach((axis) => {
    const el = slider(axis);
    if (!el) return;
    el.addEventListener("input", () => updateValueDisplay(axis));
    el.addEventListener("dblclick", () => resetSlider(axis));
    updateValueDisplay(axis);
  });

  pollStatus();
  setInterval(pollStatus, 500);
})();
