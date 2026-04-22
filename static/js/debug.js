// debug.js – Debug slider page logic + IMU readout + offset controls
(function () {
  const AXES = ["surge", "sway", "heave", "roll", "pitch", "yaw"];
  const SEND_INTERVAL_MS = 50; // 20 Hz updates while override is active
  const HISTORY_LIMIT = 120; // 12 seconds of telemetry samples

  let overrideActive = false;
  let sendTimer = null;
  let overrideState = null;
  let chartFrameScheduled = false;
  let lastTelemetry = null;

  const axisHistory = AXES.reduce((acc, axis) => {
    acc[axis] = {
      setpoint: [],
      output: [],
      error: [],
    };
    return acc;
  }, {});

  // DOM refs
  const btnEnable = document.getElementById("btn-enable");
  const btnDisable = document.getElementById("btn-disable");
  const btnResetAll = document.getElementById("btn-reset-all");
  const statusBadge = document.getElementById("debug-status");
  const rovStatus = document.getElementById("rov-status");
  const telemetryBody = document.getElementById("control-telemetry-body");
  const telemetryAge = document.getElementById("control-telemetry-age");
  const uplinkStatusBadge = document.getElementById("uplink-status-badge");
  const uplinkSequence = document.getElementById("uplink-sequence");
  const uplinkSendAge = document.getElementById("uplink-send-age");
  const uplinkAckAge = document.getElementById("uplink-ack-age");
  const uplinkUdpRx = document.getElementById("uplink-udp-rx");
  const uplinkUdpErrors = document.getElementById("uplink-udp-errors");
  const uplinkResends = document.getElementById("uplink-resends");
  const overrideStatusChip = document.getElementById("override-status-chip");
  const overrideAxes = document.getElementById("override-axes");
  const logStreamEl = document.getElementById("log-stream");
  const ATTITUDE_AXES = ["roll", "pitch", "yaw"];
  const attitudeLimits = window.debugAttitudeLimits || {};
  const attRollInput = document.getElementById("attitude-roll");
  const attPitchInput = document.getElementById("attitude-pitch");
  const attYawInput = document.getElementById("attitude-yaw");
  const btnAttitudeSend = document.getElementById("btn-attitude-send");
  const btnAttitudeClear = document.getElementById("btn-attitude-clear");
  const attitudeFeedback = document.getElementById("attitude-feedback");
  const attitudeStatus = document.getElementById("attitude-status");

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

  // --- Control telemetry helpers ---
  function pushTelemetrySample(sample) {
    if (!sample || !sample.setpoint) return;
    lastTelemetry = sample;
    AXES.forEach((axis) => {
      const store = axisHistory[axis];
      ["setpoint", "output", "error"].forEach((key) => {
        const source = sample[key] || {};
        const value = typeof source[axis] === "number" ? source[axis] : NaN;
        const series = store[key];
        series.push(value);
        if (series.length > HISTORY_LIMIT) {
          series.shift();
        }
      });
    });
    requestChartRender();
  }

  function requestChartRender() {
    if (chartFrameScheduled) return;
    chartFrameScheduled = true;
    window.requestAnimationFrame(() => {
      drawAllCharts();
      chartFrameScheduled = false;
    });
  }

  function drawAllCharts() {
    AXES.forEach((axis) => drawAxisChart(axis));
  }

  function drawAxisChart(axis) {
    const canvas = document.getElementById("chart-" + axis);
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const width = canvas.clientWidth || canvas.width;
    const height = canvas.clientHeight || canvas.height;
    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
    }
    const store = axisHistory[axis];
    const values = [...store.setpoint, ...store.output, ...store.error].filter((v) => typeof v === "number" && !Number.isNaN(v));
    const min = values.length ? Math.min(...values) : -1;
    const max = values.length ? Math.max(...values) : 1;
    const span = max - min || 1;
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    function drawSeries(series, color, width = 1.5) {
      if (!series.length) return;
      ctx.beginPath();
      ctx.strokeStyle = color;
      ctx.lineWidth = width;
      let started = false;
      series.forEach((value, idx) => {
        const normalized = Number.isNaN(value) ? null : value;
        if (normalized == null) return;
        const x = (idx / Math.max(series.length - 1, 1)) * canvas.width;
        const y = canvas.height - ((normalized - min) / span) * canvas.height;
        if (!started) {
          ctx.moveTo(x, y);
          started = true;
        } else {
          ctx.lineTo(x, y);
        }
      });
      if (started) ctx.stroke();
    }

    drawSeries(store.setpoint, "#0dcaf0", 2);
    drawSeries(store.output, "#20c997", 2);
    drawSeries(store.error, "#ffc107", 1.5);

    // midline
    ctx.beginPath();
    ctx.strokeStyle = "rgba(255,255,255,0.1)";
    ctx.lineWidth = 1;
    const midY = canvas.height - ((0 - min) / span) * canvas.height;
    ctx.moveTo(0, midY);
    ctx.lineTo(canvas.width, midY);
    ctx.stroke();
  }

  function axisOverrideActive(axis) {
    if (!overrideState || !overrideState.active) return false;
    const axes = overrideState.axes || {};
    const value = axes[axis];
    return typeof value === "number" && Math.abs(value) > 0.01;
  }

  function updateAxisStatus(axis, errorValue) {
    const badge = document.getElementById("axis-status-" + axis);
    if (!badge) return;
    const override = axisOverrideActive(axis);
    if (override) {
      badge.textContent = "OVR";
      badge.className = "badge bg-danger axis-status";
      return;
    }
    if (errorValue == null || Number.isNaN(errorValue)) {
      badge.textContent = "NA";
      badge.className = "badge bg-secondary axis-status";
      return;
    }
    const absErr = Math.abs(errorValue);
    if (absErr < 0.05) {
      badge.textContent = "LOCK";
      badge.className = "badge bg-success axis-status";
    } else if (absErr < 0.2) {
      badge.textContent = "TRACK";
      badge.className = "badge bg-warning text-dark axis-status";
    } else {
      badge.textContent = "OFF";
      badge.className = "badge bg-danger axis-status";
    }
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
      const res = await fetch("/api/debug/clear", { method: "POST" });
      return res.ok;
    } catch (e) {
      console.error("Failed to clear debug override:", e);
      return false;
    }
  }

  async function pollStatus() {
    try {
      const res = await fetch("/api/rov/status");
      const data = await res.json();
      rovStatus.textContent = JSON.stringify({
        command: data.command,
        uplink: data.uplink,
        resource: data.resource,
      }, null, 2);
    } catch (_) {
      rovStatus.textContent = "Error fetching status";
    }
  }

  function fmtMs(value) {
    if (value == null) return "--";
    return value.toFixed(0);
  }

  function fmtFloat(value, digits = 2) {
    if (value == null || Number.isNaN(value)) return "NaN";
    return value.toFixed(digits);
  }

  function updateTelemetryAgeLabel(snapshot) {
    if (!telemetryAge) return;
    const ageMs = snapshot && snapshot.timestamp ? Math.max(0, Date.now() - snapshot.timestamp * 1000) : null;
    telemetryAge.textContent = fmtMs(ageMs);
  }

  function renderTelemetryTable(snapshot) {
    if (!telemetryBody) return;
    const setpoint = (snapshot && snapshot.setpoint) || {};
    const output = (snapshot && snapshot.output) || {};
    const error = (snapshot && snapshot.error) || {};
    const frag = document.createDocumentFragment();
    AXES.forEach((axis) => {
      const tr = document.createElement("tr");
      tr.className = "telemetry-row";
      if (axisOverrideActive(axis)) tr.classList.add("override-active");
      const tdAxis = document.createElement("td");
      tdAxis.textContent = axis.toUpperCase();
      const tdSet = document.createElement("td");
      tdSet.textContent = fmtFloat(setpoint[axis]);
      const tdOut = document.createElement("td");
      tdOut.textContent = fmtFloat(output[axis]);
      const tdErr = document.createElement("td");
      tdErr.textContent = fmtFloat(error[axis]);
      tr.append(tdAxis, tdSet, tdOut, tdErr);
      frag.appendChild(tr);
      updateAxisStatus(axis, error[axis]);
    });
    telemetryBody.innerHTML = "";
    telemetryBody.appendChild(frag);
  }

  async function pollControlTelemetry() {
    try {
      const res = await fetch("/api/control/telemetry");
      const data = await res.json();
      if (!data.ok) return;
      pushTelemetrySample(data.telemetry);
      renderTelemetryTable(data.telemetry);
      updateTelemetryAgeLabel(data.telemetry);
    } catch (err) {
      console.error("control telemetry poll failed", err);
    }
  }

  async function bootstrapTelemetryHistory() {
    try {
      const res = await fetch(`/api/control/telemetry/history?limit=${HISTORY_LIMIT}`);
      const data = await res.json();
      if (!data.ok) return;
      (data.history || []).forEach((sample) => pushTelemetrySample(sample));
      if (data.history && data.history.length) {
        const latest = data.history[data.history.length - 1];
        renderTelemetryTable(latest);
        updateTelemetryAgeLabel(latest);
      }
    } catch (err) {
      console.error("bootstrap telemetry history failed", err);
    }
  }

  function renderOverrideState(state) {
    if (!overrideAxes || !overrideStatusChip) return;
    overrideState = state || null;
    const active = !!(state && state.active);
    overrideStatusChip.textContent = active ? "ACTIVE" : "INACTIVE";
    overrideStatusChip.className = `badge ${active ? "bg-danger" : "bg-secondary"}`;
    const axes = (state && state.axes) || {};
    const entries = AXES.filter((axis) => Math.abs(axes[axis] || 0) > 0.01)
      .map((axis) => `<span class="badge bg-dark me-1 mb-1">${axis}: ${fmtFloat(axes[axis])}</span>`);
    let html = entries.length ? entries.join(" ") : '<span class="text-muted">No overrides</span>';
    if (state && state.last_error) {
      html += `<div class="text-danger small mt-2">${state.last_error}</div>`;
    }
    overrideAxes.innerHTML = html;
  }

  function updateUplinkStatus(payload, udp, override) {
    if (!uplinkSequence) return;
    uplinkSequence.textContent = payload && typeof payload.sequence !== "undefined" ? payload.sequence : "--";
    uplinkSendAge.textContent = fmtMs(payload ? payload.last_send_age_ms : null);
    uplinkAckAge.textContent = fmtMs(payload ? payload.last_ack_age_ms : null);
    uplinkUdpRx.textContent = udp && typeof udp.count !== "undefined" ? udp.count : "--";
    uplinkUdpErrors.textContent = udp && typeof udp.errors !== "undefined" ? udp.errors : "--";
    uplinkResends.textContent = payload && typeof payload.watchdog_resends !== "undefined" ? payload.watchdog_resends : 0;
    const ackAge = payload && typeof payload.last_ack_age_ms !== "undefined" ? payload.last_ack_age_ms : null;
    if (ackAge == null) {
      uplinkStatusBadge.textContent = "IDLE";
      uplinkStatusBadge.className = "badge bg-secondary";
    } else if (ackAge < 1000) {
      uplinkStatusBadge.textContent = "LIVE";
      uplinkStatusBadge.className = "badge bg-success";
    } else if (ackAge < 3000) {
      uplinkStatusBadge.textContent = "STALE";
      uplinkStatusBadge.className = "badge bg-warning text-dark";
    } else {
      uplinkStatusBadge.textContent = "DEGRADED";
      uplinkStatusBadge.className = "badge bg-danger";
    }
    renderOverrideState(override);
  }

  async function pollCommandStatus() {
    try {
      const res = await fetch("/api/command/status");
      const data = await res.json();
      if (!data.ok) return;
      updateUplinkStatus(data.uplink, { count: data.udp_rx_count, errors: data.udp_rx_errors }, data.override);
    } catch (err) {
      console.error("command status poll failed", err);
    }
  }

  function renderLogs(entries) {
    if (!logStreamEl) return;
    const frag = document.createDocumentFragment();
    entries.forEach((entry) => {
      const row = document.createElement("div");
      row.className = "d-flex justify-content-between border-bottom border-secondary py-1";
      const body = document.createElement("div");
      const level = entry.level || "I";
      const badge = document.createElement("span");
      const levelMap = { I: "bg-info text-dark", W: "bg-warning text-dark", R: "bg-danger", D: "bg-secondary" };
      badge.className = `badge me-2 ${levelMap[level] || "bg-secondary"}`;
      badge.textContent = level;
      body.appendChild(badge);
      const msg = document.createElement("span");
      msg.textContent = entry.message || "";
      body.appendChild(msg);
      const ts = document.createElement("span");
      ts.className = "text-light-muted small ms-3";
      const tsValue = entry.ts ? new Date(entry.ts * 1000) : new Date();
      ts.textContent = tsValue.toLocaleTimeString();
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
      const res = await fetch("/api/logs/live?limit=50");
      const data = await res.json();
      if (!data.ok) return;
      renderLogs(data.logs || []);
    } catch (err) {
      console.error("log stream poll failed", err);
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

  function resetOverrideUi() {
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
  }

  function disableOverride() {
    resetOverrideUi();
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
  pollCommandStatus();
  setInterval(pollCommandStatus, 1000);
  bootstrapTelemetryHistory();
  pollControlTelemetry();
  setInterval(pollControlTelemetry, 200);
  pollLogs();
  setInterval(pollLogs, 1500);

  // IMU Live Readout
  const imuStatus = document.getElementById("imu-status");
  const imuYaw = document.getElementById("imu-yaw");
  const imuPitch = document.getElementById("imu-pitch");
  const imuRoll = document.getElementById("imu-roll");
  const imuPktCount = document.getElementById("imu-pkt-count");
  const imuAge = document.getElementById("imu-age");
  const imuTareInfo = document.getElementById("imu-tare-info");

  function fmtDeg(v) {
    const n = parseFloat(v);
    if (isNaN(n)) return "--.-\u00B0";
    return (n >= 0 ? "+" : "") + n.toFixed(1) + "\u00B0";
  }

  async function pollIMU() {
    try {
      const res = await fetch("/api/imu/status");
      const data = await res.json();
      if (!data.ok) return;

      const s = data.stats;
      const d = s.last_data;

      imuYaw.textContent = fmtDeg(d.yaw);
      imuPitch.textContent = fmtDeg(d.pitch);
      imuRoll.textContent = fmtDeg(d.roll);
      imuPktCount.textContent = s.packet_count;
      imuAge.textContent = s.age_ms != null ? s.age_ms : "--";

      // Color based on age
      if (s.age_ms != null && s.age_ms < 500) {
        imuStatus.textContent = "LIVE";
        imuStatus.className = "badge bg-success me-2";
      } else if (s.age_ms != null && s.age_ms < 2000) {
        imuStatus.textContent = "STALE";
        imuStatus.className = "badge bg-warning me-2";
      } else {
        imuStatus.textContent = "NO DATA";
        imuStatus.className = "badge bg-secondary me-2";
      }

      // Tare info
      const t = s.tare_offset;
      if (t && (t.yaw !== 0 || t.pitch !== 0 || t.roll !== 0)) {
        imuTareInfo.textContent =
          "Y:" + t.yaw.toFixed(1) + " P:" + t.pitch.toFixed(1) + " R:" + t.roll.toFixed(1);
      } else {
        imuTareInfo.textContent = "none";
      }
    } catch (_) {
      /* silent */
    }
  }

  document.getElementById("btn-tare").addEventListener("click", async () => {
    try {
      await fetch("/api/imu/tare", { method: "POST" });
    } catch (e) {
      console.error("Tare failed:", e);
    }
  });

  document.getElementById("btn-clear-tare").addEventListener("click", async () => {
    try {
      await fetch("/api/imu/tare", { method: "DELETE" });
    } catch (e) {
      console.error("Clear tare failed:", e);
    }
  });

  pollIMU();
  setInterval(pollIMU, 200);

  // IMU Offset from Mass Center
  const offsetX = document.getElementById("offset-x");
  const offsetY = document.getElementById("offset-y");
  const offsetZ = document.getElementById("offset-z");
  const offsetFeedback = document.getElementById("offset-feedback");

  // Load current offset on page load
  async function loadOffset() {
    try {
      const res = await fetch("/api/imu/offset");
      const data = await res.json();
      if (data.ok && data.offset) {
        offsetX.value = data.offset.x;
        offsetY.value = data.offset.y;
        offsetZ.value = data.offset.z;
      }
    } catch (_) {
      /* silent */
    }
  }

  document.getElementById("btn-save-offset").addEventListener("click", async () => {
    try {
      const res = await fetch("/api/imu/offset", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          x: parseFloat(offsetX.value) || 0,
          y: parseFloat(offsetY.value) || 0,
          z: parseFloat(offsetZ.value) || 0,
        }),
      });
      if (!res.ok) {
        offsetFeedback.textContent = "Server error: " + res.status;
        offsetFeedback.className = "small mt-2 text-danger";
        return;
      }
      const data = await res.json();
      if (data.ok) {
        offsetFeedback.textContent = "Offset saved: X=" + data.offset.x + " Y=" + data.offset.y + " Z=" + data.offset.z;
        offsetFeedback.className = "small mt-2 text-success";
      } else {
        offsetFeedback.textContent = "Failed to save offset";
        offsetFeedback.className = "small mt-2 text-danger";
      }
    } catch (e) {
      offsetFeedback.textContent = "Error: " + e.message;
      offsetFeedback.className = "small mt-2 text-danger";
    }
  });

  loadOffset();

  // ============================
  // IMU Axis Mapping
  // ============================
  const axesYaw = document.getElementById("axes-yaw");
  const axesPitch = document.getElementById("axes-pitch");
  const axesRoll = document.getElementById("axes-roll");
  const axesFeedback = document.getElementById("axes-feedback");

  async function loadAxes() {
    try {
      const res = await fetch("/api/imu/axes");
      const data = await res.json();
      if (data.ok && data.axes) {
        axesYaw.value = data.axes.yaw;
        axesPitch.value = data.axes.pitch;
        axesRoll.value = data.axes.roll;
      }
    } catch (_) {
      /* silent */
    }
  }

  document.getElementById("btn-save-axes").addEventListener("click", async () => {
    try {
      const res = await fetch("/api/imu/axes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          yaw: axesYaw.value,
          pitch: axesPitch.value,
          roll: axesRoll.value,
        }),
      });
      if (!res.ok) {
        axesFeedback.textContent = "Server error: " + res.status;
        axesFeedback.className = "small mt-2 text-danger";
        return;
      }
      const data = await res.json();
      if (data.ok) {
        axesFeedback.textContent = "Orientation saved — takes effect immediately";
        axesFeedback.className = "small mt-2 text-success";
      } else {
        axesFeedback.textContent = "Failed to save orientation";
        axesFeedback.className = "small mt-2 text-danger";
      }
    } catch (e) {
      axesFeedback.textContent = "Error: " + e.message;
      axesFeedback.className = "small mt-2 text-danger";
    }
  });

  loadAxes();

  // ============================
  // Accelerometer Axis Mapping
  // ============================
  const accelX = document.getElementById("accel-x");
  const accelY = document.getElementById("accel-y");
  const accelZ = document.getElementById("accel-z");
  const accelFeedback = document.getElementById("accel-feedback");

  async function loadAccelAxes() {
    try {
      const res = await fetch("/api/imu/accel_axes");
      const data = await res.json();
      if (data.ok && data.accel_axes) {
        accelX.value = data.accel_axes.x;
        accelY.value = data.accel_axes.y;
        accelZ.value = data.accel_axes.z;
      }
    } catch (_) {
      /* silent */
    }
  }

  document.getElementById("btn-save-accel").addEventListener("click", async () => {
    try {
      const res = await fetch("/api/imu/accel_axes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          x: accelX.value,
          y: accelY.value,
          z: accelZ.value,
        }),
      });
      if (!res.ok) {
        accelFeedback.textContent = "Server error: " + res.status;
        accelFeedback.className = "small mt-2 text-danger";
        return;
      }
      const data = await res.json();
      if (data.ok) {
        accelFeedback.textContent = "Accel mapping saved — takes effect immediately";
        accelFeedback.className = "small mt-2 text-success";
      } else {
        accelFeedback.textContent = "Failed to save accel mapping";
        accelFeedback.className = "small mt-2 text-danger";
      }
    } catch (e) {
      accelFeedback.textContent = "Error: " + e.message;
      accelFeedback.className = "small mt-2 text-danger";
    }
  });

  loadAccelAxes();

  // --- PID Configuration ---
  const PID_AXES = ["surge", "sway", "heave", "roll", "pitch", "yaw"];
  const PID_GAINS = ["kp", "ki", "kd"];
  const pidStatus = document.getElementById("pid-status");
  const btnPidRequest = document.getElementById("btn-pid-request");
  const btnPidSend = document.getElementById("btn-pid-send");
  const btnPidReset = document.getElementById("btn-pid-reset");

  function setPidStatus(text, cls) {
    pidStatus.textContent = text;
    pidStatus.className = "badge me-2 " + cls;
  }

  function fillPidFields(gains) {
    PID_AXES.forEach(function (axis) {
      PID_GAINS.forEach(function (g) {
        var el = document.getElementById("pid-" + axis + "-" + g);
        if (el && gains[axis]) el.value = gains[axis][g];
      });
    });
  }

  function readPidFields() {
    var gains = {};
    PID_AXES.forEach(function (axis) {
      gains[axis] = {};
      PID_GAINS.forEach(function (g) {
        var el = document.getElementById("pid-" + axis + "-" + g);
        gains[axis][g] = el ? parseFloat(el.value) || 0 : 0;
      });
    });
    return gains;
  }

  btnPidRequest.addEventListener("click", async function () {
    setPidStatus("REQUESTING...", "bg-warning text-dark");
    btnPidRequest.disabled = true;
    try {
      var res = await fetch("/api/pid/gains");
      var data = await res.json();
      if (data.ok) {
        fillPidFields(data.gains);
        setPidStatus("LOADED", "bg-success");
      } else {
        setPidStatus("NO RESPONSE", "bg-danger");
      }
    } catch (e) {
      setPidStatus("ERROR", "bg-danger");
      console.error("PID request failed:", e);
    }
    btnPidRequest.disabled = false;
  });

  btnPidSend.addEventListener("click", async function () {
    setPidStatus("SENDING...", "bg-warning text-dark");
    btnPidSend.disabled = true;
    try {
      var res = await fetch("/api/pid/gains", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(readPidFields()),
      });
      var data = await res.json();
      if (data.ok) {
        fillPidFields(data.gains);
        var label = data.attempts > 1
          ? "CONFIRMED (retry " + data.attempts + "/3)"
          : "CONFIRMED";
        setPidStatus(label, "bg-success");
      } else {
        setPidStatus(data.error || "NO RESPONSE", "bg-danger");
      }
    } catch (e) {
      setPidStatus("ERROR", "bg-danger");
      console.error("PID send failed:", e);
    }
    btnPidSend.disabled = false;
  });

  btnPidReset.addEventListener("click", async function () {
    var zeros = {};
    PID_AXES.forEach(function (axis) {
      zeros[axis] = { kp: 0, ki: 0, kd: 0 };
    });
    fillPidFields(zeros);
    setPidStatus("SENDING...", "bg-warning text-dark");
    btnPidReset.disabled = true;
    try {
      var res = await fetch("/api/pid/gains", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(zeros),
      });
      var data = await res.json();
      if (data.ok) {
        fillPidFields(data.gains);
        setPidStatus("RESET OK", "bg-success");
      } else {
        setPidStatus(data.error || "NO RESPONSE", "bg-danger");
      }
    } catch (e) {
      setPidStatus("ERROR", "bg-danger");
      console.error("PID reset failed:", e);
    }
    btnPidReset.disabled = false;
  });

  // --- PID Config Save / Load ---
  var pidConfigName = document.getElementById("pid-config-name");
  var pidConfigSelect = document.getElementById("pid-config-select");
  var btnPidSave = document.getElementById("btn-pid-save");
  var btnPidLoad = document.getElementById("btn-pid-load");
  var btnPidDelete = document.getElementById("btn-pid-delete");
  var pidConfigStatus = document.getElementById("pid-config-status");

  function setConfigStatus(text, cls) {
    pidConfigStatus.textContent = text;
    pidConfigStatus.className = "badge small " + cls;
  }

  async function refreshConfigList() {
    try {
      var res = await fetch("/api/pid/configs");
      var data = await res.json();
      var names = data.configs || [];
      pidConfigSelect.innerHTML = '<option value="">-- select --</option>';
      names.forEach(function (n) {
        var opt = document.createElement("option");
        opt.value = n;
        opt.textContent = n;
        pidConfigSelect.appendChild(opt);
      });
    } catch (e) {
      console.error("Failed to list PID configs:", e);
    }
  }

  btnPidSave.addEventListener("click", async function () {
    var name = pidConfigName.value.trim();
    if (!name) {
      setConfigStatus("Enter a name", "bg-warning text-dark");
      return;
    }
    try {
      var res = await fetch("/api/pid/configs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name, gains: readPidFields() }),
      });
      var data = await res.json();
      if (data.ok) {
        setConfigStatus("Saved", "bg-success");
        refreshConfigList();
      } else {
        setConfigStatus(data.error || "Error", "bg-danger");
      }
    } catch (e) {
      setConfigStatus("Error", "bg-danger");
    }
  });

  btnPidLoad.addEventListener("click", async function () {
    var name = pidConfigSelect.value;
    if (!name) {
      setConfigStatus("Select a config", "bg-warning text-dark");
      return;
    }
    try {
      var res = await fetch("/api/pid/configs/" + encodeURIComponent(name));
      var data = await res.json();
      if (data.ok) {
        fillPidFields(data.gains);
        pidConfigName.value = name;
        setConfigStatus("Loaded", "bg-success");
      } else {
        setConfigStatus(data.error || "Not found", "bg-danger");
      }
    } catch (e) {
      setConfigStatus("Error", "bg-danger");
    }
  });

  btnPidDelete.addEventListener("click", async function () {
    var name = pidConfigSelect.value;
    if (!name) {
      setConfigStatus("Select a config", "bg-warning text-dark");
      return;
    }
    if (!confirm('Delete config "' + name + '"?')) return;
    try {
      var res = await fetch("/api/pid/configs/" + encodeURIComponent(name), {
        method: "DELETE",
      });
      var data = await res.json();
      if (data.ok) {
        setConfigStatus("Deleted", "bg-success");
        refreshConfigList();
      } else {
        setConfigStatus(data.error || "Error", "bg-danger");
      }
    } catch (e) {
      setConfigStatus("Error", "bg-danger");
    }
  });

  // Load config list on page load
  refreshConfigList();

  // --- Attitude Setpoint Override ---
  function setAttitudeStatus(text, cls) {
    attitudeStatus.textContent = text;
    attitudeStatus.className = "badge " + cls;
  }

  btnAttitudeSend.addEventListener("click", async function () {
    var payload = {};
    var roll = parseFloat(attRollInput.value);
    var pitch = parseFloat(attPitchInput.value);
    var yaw = parseFloat(attYawInput.value);
    if (!isNaN(roll)) payload.roll = roll;
    if (!isNaN(pitch)) payload.pitch = pitch;
    if (!isNaN(yaw)) payload.yaw = yaw;
    if (Object.keys(payload).length === 0) {
      attitudeFeedback.textContent = "Enter at least one value.";
      attitudeFeedback.className = "small text-warning ms-auto";
      return;
    }
    setAttitudeStatus("SENDING…", "bg-warning text-dark");
    btnAttitudeSend.disabled = true;
    try {
      var res = await fetch("/api/debug/attitude_setpoint", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      var data = await res.json();
      if (data.ok) {
        var sent = data.sent || {};
        var parts = Object.entries(sent).map(function (kv) {
          return kv[0] + "=" + kv[1].toFixed(1) + "°";
        });
        attitudeFeedback.textContent = "Sent: " + parts.join(", ");
        attitudeFeedback.className = "small text-success ms-auto";
        setAttitudeStatus("ACTIVE", "bg-danger");
      } else {
        attitudeFeedback.textContent = data.error || "Failed";
        attitudeFeedback.className = "small text-danger ms-auto";
        setAttitudeStatus("ERROR", "bg-danger");
      }
    } catch (e) {
      attitudeFeedback.textContent = "Error: " + e.message;
      attitudeFeedback.className = "small text-danger ms-auto";
      setAttitudeStatus("ERROR", "bg-danger");
    }
    btnAttitudeSend.disabled = false;
  });

  btnAttitudeClear.addEventListener("click", async function () {
    setAttitudeStatus("CLEARING…", "bg-warning text-dark");
    btnAttitudeClear.disabled = true;
    try {
      var res = await fetch("/api/debug/clear", { method: "POST" });
      var data = await res.json();
      if (data.ok) {
        attitudeFeedback.textContent = "Override cleared.";
        attitudeFeedback.className = "small text-light-muted ms-auto";
        setAttitudeStatus("IDLE", "bg-secondary");
      } else {
        attitudeFeedback.textContent = data.error || "Failed to clear";
        attitudeFeedback.className = "small text-danger ms-auto";
        setAttitudeStatus("ERROR", "bg-danger");
      }
    } catch (e) {
      attitudeFeedback.textContent = "Error: " + e.message;
      attitudeFeedback.className = "small text-danger ms-auto";
      setAttitudeStatus("ERROR", "bg-danger");
    }
    btnAttitudeClear.disabled = false;
  });
})();
