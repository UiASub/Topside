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
  const telemetryBody = document.getElementById("control-telemetry-body");
  const telemetryAge = document.getElementById("control-telemetry-age");
  const logStreamEl = document.getElementById("log-stream");

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

  function fmtMs(value) {
    if (value == null || Number.isNaN(value)) return "--";
    return value.toFixed(0);
  }

  function fmtFloat(value) {
    if (value == null || Number.isNaN(value)) return "NaN";
    return Number(value).toFixed(2);
  }

  function renderTelemetryTable(snapshot) {
    if (!telemetryBody) return;
    const setpoint = (snapshot && snapshot.setpoint) || {};
    const output = (snapshot && snapshot.output) || {};
    const error = (snapshot && snapshot.error) || {};
    const frag = document.createDocumentFragment();
    AXES.forEach((axis) => {
      const tr = document.createElement("tr");
      [axis.toUpperCase(), fmtFloat(setpoint[axis]), fmtFloat(output[axis]), fmtFloat(error[axis])].forEach((text) => {
        const td = document.createElement("td");
        td.textContent = text;
        tr.appendChild(td);
      });
      frag.appendChild(tr);
    });
    telemetryBody.innerHTML = "";
    telemetryBody.appendChild(frag);
  }

  async function pollControlTelemetry() {
    try {
      const res = await fetch("/api/control/telemetry", { cache: "no-store" });
      const data = await res.json();
      if (!data.ok) return;
      const snapshot = data.telemetry || {};
      renderTelemetryTable(snapshot);
      if (telemetryAge) {
        const ageMs = snapshot.timestamp ? Math.max(0, Date.now() - snapshot.timestamp * 1000) : null;
        telemetryAge.textContent = fmtMs(ageMs);
      }
    } catch (error) {
      console.error("control telemetry poll failed", error);
    }
  }

  function renderLogs(entries) {
    if (!logStreamEl) return;
    const frag = document.createDocumentFragment();
    entries.forEach((entry) => {
      const row = document.createElement("div");
      row.className = "d-flex justify-content-between border-bottom border-secondary py-1";

      const body = document.createElement("div");
      const badge = document.createElement("span");
      const level = entry.level || "I";
      const levelMap = { I: "bg-info text-dark", W: "bg-warning text-dark", R: "bg-danger", D: "bg-secondary" };
      badge.className = "badge me-2 " + (levelMap[level] || "bg-secondary");
      badge.textContent = level;
      body.appendChild(badge);

      const msg = document.createElement("span");
      msg.textContent = entry.message || "";
      body.appendChild(msg);

      const ts = document.createElement("span");
      ts.className = "text-light-muted small ms-3";
      ts.textContent = (entry.ts ? new Date(entry.ts * 1000) : new Date()).toLocaleTimeString();

      row.appendChild(body);
      row.appendChild(ts);
      frag.appendChild(row);
    });
    logStreamEl.innerHTML = "";
    logStreamEl.appendChild(frag);
    logStreamEl.scrollTop = logStreamEl.scrollHeight;
  }

  async function pollLogs() {
    try {
      const res = await fetch("/api/logs/live?limit=50", { cache: "no-store" });
      const data = await res.json();
      if (data.ok) renderLogs(data.logs || []);
    } catch (error) {
      console.error("log stream poll failed", error);
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
  pollControlTelemetry();
  setInterval(pollControlTelemetry, 500);
  pollLogs();
  setInterval(pollLogs, 1500);
})();
