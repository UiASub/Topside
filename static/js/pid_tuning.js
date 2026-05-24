// PID tuning page controls.
(function () {
  "use strict";

  const AXES = ["surge", "sway", "heave", "roll", "pitch", "yaw"];
  const ROT_AXES = ["roll", "pitch", "yaw"];
  const DISPLAY_AXES = ["heave", "roll", "pitch", "yaw"];
  const PID_GAINS = ["kp", "ki", "kd"];
  const SEND_INTERVAL_MS = 50;

  const attitudeLimits = window.pidTuningAttitudeLimits || { roll: 180, pitch: 90, yaw: 180 };
  let overrideActive = false;
  let sendTimer = null;
  let latestImu = {};
  let latestDepth = {};
  let latestTelemetry = null;
  const localSetpoints = { roll: NaN, pitch: NaN, yaw: NaN };

  const pageStatus = document.getElementById("pid-page-status");
  const linkStatus = document.getElementById("pid-link-status");
  const frameStatus = document.getElementById("frame-lock-status");
  const imuAge = document.getElementById("pid-imu-age");
  const pidStatus = document.getElementById("pid-status");
  const setpointStatus = document.getElementById("setpoint-status");
  const setpointFeedback = document.getElementById("setpoint-feedback");
  const telemetryAge = document.getElementById("telemetry-age");
  const telemetryBody = document.getElementById("pid-telemetry-body");
  const rovStatus = document.getElementById("rov-status");

  function isFiniteNumber(value) {
    return typeof value === "number" && Number.isFinite(value);
  }

  function fmt(value, digits) {
    if (!isFiniteNumber(value)) return "--";
    return value.toFixed(digits == null ? 2 : digits);
  }

  function normalizeAngle(value) {
    let wrapped = ((value + 180) % 360) - 180;
    if (wrapped === -180 && value > 0) wrapped = 180;
    return wrapped;
  }

  function angleError(setpoint, position) {
    if (!isFiniteNumber(setpoint) || !isFiniteNumber(position)) return NaN;
    return normalizeAngle(setpoint - position);
  }

  function setBadge(el, text, cls) {
    if (!el) return;
    el.textContent = text;
    el.className = "badge " + cls;
  }

  function setPageStatus(text, cls) {
    setBadge(pageStatus, text, cls || "bg-secondary");
  }

  function setPidStatus(text, cls) {
    setBadge(pidStatus, text, cls || "bg-secondary");
  }

  function setSetpointStatus(text, cls) {
    setBadge(setpointStatus, text, cls || "bg-secondary");
  }

  function setFeedback(text, cls) {
    if (!setpointFeedback) return;
    setpointFeedback.textContent = text;
    setpointFeedback.className = "pid-feedback " + (cls || "");
  }

  function clampSetpoint(axis, value) {
    const limit = Number(attitudeLimits[axis] || 180);
    let next = Number(value);
    if (!Number.isFinite(next)) return NaN;
    if (axis === "roll" || axis === "yaw") next = normalizeAngle(next);
    return Math.max(-limit, Math.min(limit, next));
  }

  function getTelemetrySetpoint(axis) {
    const fromTelemetry = latestTelemetry && latestTelemetry.setpoint ? Number(latestTelemetry.setpoint[axis]) : NaN;
    if (Number.isFinite(fromTelemetry)) return fromTelemetry;
    return localSetpoints[axis];
  }

  function updateTelemetryTable() {
    if (!telemetryBody) return;
    const frag = document.createDocumentFragment();
    DISPLAY_AXES.forEach((axis) => {
      const setpoint = getTelemetrySetpoint(axis);
      const position = axis === "heave" ? -Number(latestDepth.dpt) : Number(latestImu[axis]);
      const error = axis === "heave" ? setpoint - position : angleError(setpoint, position);
      const tr = document.createElement("tr");
      const tdAxis = document.createElement("td");
      const tdSet = document.createElement("td");
      const tdPos = document.createElement("td");
      const tdErr = document.createElement("td");
      tdAxis.textContent = axis.toUpperCase();
      tdSet.textContent = fmt(setpoint, 2);
      tdPos.textContent = fmt(position, 2);
      tdErr.textContent = fmt(error, 2);
      const warnLimit = axis === "heave" ? 0.15 : 10;
      const dangerLimit = axis === "heave" ? 0.35 : 25;
      if (isFiniteNumber(error) && Math.abs(error) > warnLimit) tdErr.className = "text-warning";
      if (isFiniteNumber(error) && Math.abs(error) > dangerLimit) tdErr.className = "text-danger";
      tr.append(tdAxis, tdSet, tdPos, tdErr);
      frag.appendChild(tr);
    });
    telemetryBody.innerHTML = "";
    telemetryBody.appendChild(frag);
  }

  function updateTelemetryAge(snapshot) {
    if (!telemetryAge) return;
    const ageMs = snapshot && snapshot.timestamp ? Math.max(0, Date.now() - snapshot.timestamp * 1000) : null;
    if (ageMs == null) setBadge(telemetryAge, "NO TELEMETRY", "bg-secondary");
    else if (ageMs < 750) setBadge(telemetryAge, ageMs.toFixed(0) + " ms", "bg-success");
    else if (ageMs < 2500) setBadge(telemetryAge, ageMs.toFixed(0) + " ms", "bg-warning text-dark");
    else setBadge(telemetryAge, "STALE", "bg-danger");
  }

  async function pollImuAndTelemetry() {
    const imuReq = fetch("/api/imu/status").then((res) => res.json());
    const telemetryReq = fetch("/api/control/telemetry").then((res) => res.json());
    const depthReq = fetch("/api/depth").then((res) => res.json());
    const frameReq = fetch("/api/frame/status").then((res) => res.json());
    const results = await Promise.allSettled([imuReq, telemetryReq, depthReq, frameReq]);

    if (results[0].status === "fulfilled" && results[0].value.ok) {
      const stats = results[0].value.stats || {};
      const data = stats.last_data || {};
      latestImu = {
        roll: Number(data.roll),
        pitch: Number(data.pitch),
        yaw: Number(data.yaw),
      };
      if (imuAge) imuAge.textContent = stats.age_ms != null ? stats.age_ms : "--";
    }

    if (results[1].status === "fulfilled" && results[1].value.ok) {
      latestTelemetry = results[1].value.telemetry || null;
      updateTelemetryAge(latestTelemetry);
    }

    if (results[2].status === "fulfilled") {
      latestDepth = results[2].value || {};
    }

    if (results[3].status === "fulfilled" && results[3].value.ok) {
      updateFrameStatus(results[3].value.state || {}, results[3].value.telemetry || {});
    }

    updateTelemetryTable();
  }

  function updateFrameStatus(state, telemetry) {
    const locked = Boolean((telemetry && telemetry.locked) || (state && state.active));
    setBadge(frameStatus, locked ? "FRAME LOCKED" : "FRAME FREE", locked ? "bg-info text-dark" : "bg-secondary");
  }

  async function sendFrameCommand(action) {
    const endpoint = action === "lock" ? "/api/frame/lock" : "/api/frame/unlock";
    try {
      const res = await fetch(endpoint, { method: "POST" });
      const data = await res.json();
      if (data.ok) {
        updateFrameStatus(data.state || {}, {});
      } else {
        setBadge(frameStatus, "FRAME ERROR", "bg-danger");
      }
    } catch (err) {
      setBadge(frameStatus, "FRAME ERROR", "bg-danger");
      console.error("Frame command failed:", err);
    }
  }

  function getSliderValue(axis) {
    const slider = document.getElementById("slider-" + axis);
    return slider ? parseInt(slider.value, 10) / 100 : 0;
  }

  function getAllSliderValues() {
    const values = {};
    AXES.forEach((axis) => {
      values[axis] = getSliderValue(axis);
    });
    return values;
  }

  function updateValueDisplay(axis) {
    const value = getSliderValue(axis);
    const label = document.getElementById("val-" + axis);
    const slider = document.getElementById("slider-" + axis);
    if (label) label.textContent = value.toFixed(2);
    if (!slider) return;
    slider.classList.remove("positive", "negative", "zero");
    if (value > 0.005) slider.classList.add("positive");
    else if (value < -0.005) slider.classList.add("negative");
    else slider.classList.add("zero");
  }

  function resetSlider(axis) {
    const slider = document.getElementById("slider-" + axis);
    if (!slider) return;
    slider.value = 0;
    updateValueDisplay(axis);
  }

  async function sendOverride() {
    if (!overrideActive) return;
    try {
      await fetch("/api/debug/override", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(getAllSliderValues()),
      });
    } catch (err) {
      console.error("Failed to send override:", err);
    }
  }

  function resetOverrideUi() {
    overrideActive = false;
    if (sendTimer) {
      clearInterval(sendTimer);
      sendTimer = null;
    }
    const btnEnable = document.getElementById("btn-enable");
    const btnDisable = document.getElementById("btn-disable");
    const status = document.getElementById("debug-status");
    if (btnEnable) btnEnable.disabled = false;
    if (btnDisable) btnDisable.disabled = true;
    setBadge(status, "INACTIVE", "bg-secondary");
  }

  function enableOverride() {
    if (overrideActive) return;
    overrideActive = true;
    const btnEnable = document.getElementById("btn-enable");
    const btnDisable = document.getElementById("btn-disable");
    const status = document.getElementById("debug-status");
    if (btnEnable) btnEnable.disabled = true;
    if (btnDisable) btnDisable.disabled = false;
    setBadge(status, "ACTIVE", "bg-danger");
    sendOverride();
    sendTimer = setInterval(sendOverride, SEND_INTERVAL_MS);
  }

  async function disableOverride() {
    resetOverrideUi();
    try {
      await fetch("/api/debug/clear", { method: "POST" });
    } catch (err) {
      console.error("Failed to clear override:", err);
    }
  }

  function activateNeutralOverride() {
    AXES.forEach(resetSlider);
    enableOverride();
  }

  function readPidFields() {
    const gains = {};
    AXES.forEach((axis) => {
      gains[axis] = {};
      PID_GAINS.forEach((gain) => {
        const el = document.getElementById("pid-" + axis + "-" + gain);
        gains[axis][gain] = el ? parseFloat(el.value) || 0 : 0;
      });
    });
    return gains;
  }

  function fillPidFields(gains) {
    AXES.forEach((axis) => {
      PID_GAINS.forEach((gain) => {
        const el = document.getElementById("pid-" + axis + "-" + gain);
        if (el && gains && gains[axis] && gains[axis][gain] != null) {
          el.value = gains[axis][gain];
        }
      });
    });
  }

  function zeroGainPayload() {
    const zeros = {};
    AXES.forEach((axis) => {
      zeros[axis] = { kp: 0, ki: 0, kd: 0 };
    });
    return zeros;
  }

  async function requestPidGains() {
    setPidStatus("REQUESTING", "bg-warning text-dark");
    const btn = document.getElementById("btn-pid-request");
    if (btn) btn.disabled = true;
    try {
      const res = await fetch("/api/pid/gains");
      const data = await res.json();
      if (data.ok) {
        fillPidFields(data.gains);
        setPidStatus("LOADED", "bg-success");
      } else {
        setPidStatus("NO RESPONSE", "bg-danger");
      }
    } catch (err) {
      setPidStatus("ERROR", "bg-danger");
      console.error("PID request failed:", err);
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  async function sendPidGains() {
    setPidStatus("SENDING", "bg-warning text-dark");
    const btn = document.getElementById("btn-pid-send");
    if (btn) btn.disabled = true;
    try {
      const res = await fetch("/api/pid/gains", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(readPidFields()),
      });
      const data = await res.json();
      if (data.ok) {
        fillPidFields(data.gains);
        setPidStatus(data.attempts > 1 ? "CONFIRMED RETRY " + data.attempts : "CONFIRMED", "bg-success");
      } else {
        setPidStatus(data.error || "NO RESPONSE", "bg-danger");
      }
    } catch (err) {
      setPidStatus("ERROR", "bg-danger");
      console.error("PID send failed:", err);
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  async function zeroAllPidAndThrusters() {
    activateNeutralOverride();
    fillPidFields(zeroGainPayload());
    setPidStatus("NEUTRALIZING", "bg-warning text-dark");
    setPageStatus("NEUTRALIZING", "bg-warning text-dark");
    document.querySelectorAll(".js-zero-all-pid").forEach((btn) => {
      btn.disabled = true;
    });
    try {
      const res = await fetch("/api/pid/zero_all", { method: "POST" });
      const data = await res.json().catch(() => ({}));
      if (data.gains) fillPidFields(data.gains);
      if (res.ok && data.ok) {
        setPidStatus("ZERO CONFIRMED", "bg-success");
        setPageStatus("NEUTRAL HOLD", "bg-danger");
      } else {
        setPidStatus("NEUTRAL, PID NO REPLY", "bg-danger");
        setPageStatus("NEUTRAL, CHECK MCU", "bg-danger");
      }
    } catch (err) {
      setPidStatus("NEUTRAL, ERROR", "bg-danger");
      setPageStatus("NEUTRAL, ERROR", "bg-danger");
      console.error("Zero PID failed:", err);
    } finally {
      document.querySelectorAll(".js-zero-all-pid").forEach((btn) => {
        btn.disabled = false;
      });
    }
  }

  function fillSetpointFields(setpoints) {
    ROT_AXES.forEach((axis) => {
      const value = setpoints && Number(setpoints[axis]);
      if (Number.isFinite(value)) {
        localSetpoints[axis] = value;
        const el = document.getElementById("setpoint-" + axis);
        if (el) el.value = value.toFixed(1);
      }
    });
  }

  async function startPid() {
    activateNeutralOverride();
    setSetpointStatus("STARTING", "bg-warning text-dark");
    setPageStatus("STARTING PID", "bg-warning text-dark");
    document.querySelectorAll(".js-start-pid").forEach((btn) => {
      btn.disabled = true;
    });
    try {
      const res = await fetch("/api/pid/start", { method: "POST" });
      const data = await res.json();
      if (data.ok) {
        fillSetpointFields(data.setpoints || {});
        setSetpointStatus("ACTIVE", "bg-danger");
        setPageStatus("PID HOLD ACTIVE", "bg-success");
        setFeedback("Started from current IMU attitude and current depth with neutral manual command axes.", "text-success");
      } else {
        setSetpointStatus("BLOCKED", "bg-danger");
        setPageStatus("START BLOCKED", "bg-danger");
        setFeedback(data.error || "Start failed.", "text-danger");
      }
    } catch (err) {
      setSetpointStatus("ERROR", "bg-danger");
      setPageStatus("START ERROR", "bg-danger");
      setFeedback("Error: " + err.message, "text-danger");
    } finally {
      document.querySelectorAll(".js-start-pid").forEach((btn) => {
        btn.disabled = false;
      });
    }
  }

  function readSetpointInputs() {
    const payload = {};
    ROT_AXES.forEach((axis) => {
      const el = document.getElementById("setpoint-" + axis);
      if (!el || el.value === "") return;
      const value = clampSetpoint(axis, parseFloat(el.value));
      if (Number.isFinite(value)) {
        payload[axis] = value;
        el.value = value.toFixed(1);
      }
    });
    return payload;
  }

  async function sendSetpoints() {
    const payload = readSetpointInputs();
    if (!Object.keys(payload).length) {
      setFeedback("Enter at least one angle setpoint.", "text-warning");
      return;
    }
    setSetpointStatus("SENDING", "bg-warning text-dark");
    try {
      const res = await fetch("/api/pid/setpoints", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (data.ok) {
        fillSetpointFields(data.sent || {});
        setSetpointStatus("ACTIVE", "bg-danger");
        setFeedback("Sent setpoints: " + Object.entries(data.sent || {}).map(([k, v]) => k + "=" + v.toFixed(1)).join(", "), "text-success");
      } else {
        setSetpointStatus("ERROR", "bg-danger");
        setFeedback(data.error || "Setpoint send failed.", "text-danger");
      }
    } catch (err) {
      setSetpointStatus("ERROR", "bg-danger");
      setFeedback("Error: " + err.message, "text-danger");
    }
  }

  async function clearSetpoints() {
    try {
      await fetch("/api/debug/clear", { method: "POST" });
      ROT_AXES.forEach((axis) => {
        localSetpoints[axis] = NaN;
      });
      resetOverrideUi();
      setSetpointStatus("IDLE", "bg-secondary");
      setPageStatus("READY", "bg-secondary");
      setFeedback("Setpoints cleared.", "text-light");
    } catch (err) {
      setFeedback("Error: " + err.message, "text-danger");
    }
  }

  async function pollRovStatus() {
    try {
      const res = await fetch("/api/rov/status");
      const data = await res.json();
      if (rovStatus) {
        rovStatus.textContent = JSON.stringify(
          { command: data.command, uplink: data.uplink, resource: data.resource },
          null,
          2
        );
      }
      const ackAge = data.uplink && isFiniteNumber(data.uplink.last_ack_age_ms) ? data.uplink.last_ack_age_ms : null;
      if (ackAge == null) setBadge(linkStatus, "LINK IDLE", "bg-secondary");
      else if (ackAge < 1000) setBadge(linkStatus, "LINK LIVE", "bg-success");
      else if (ackAge < 3000) setBadge(linkStatus, "LINK STALE", "bg-warning text-dark");
      else setBadge(linkStatus, "LINK DEGRADED", "bg-danger");
    } catch (err) {
      if (rovStatus) rovStatus.textContent = "Error fetching status";
      setBadge(linkStatus, "LINK ERROR", "bg-danger");
    }
  }

  async function refreshConfigList() {
    const select = document.getElementById("pid-config-select");
    if (!select) return;
    try {
      const res = await fetch("/api/pid/configs");
      const data = await res.json();
      select.innerHTML = '<option value="">Load tune</option>';
      (data.configs || []).forEach((name) => {
        const opt = document.createElement("option");
        opt.value = name;
        opt.textContent = name;
        select.appendChild(opt);
      });
    } catch (err) {
      console.error("Failed to list PID configs:", err);
    }
  }

  function setConfigStatus(text, cls) {
    setBadge(document.getElementById("pid-config-status"), text, cls || "bg-secondary");
  }

  async function saveConfig() {
    const nameEl = document.getElementById("pid-config-name");
    const name = nameEl ? nameEl.value.trim() : "";
    if (!name) {
      setConfigStatus("Name", "bg-warning text-dark");
      return;
    }
    try {
      const res = await fetch("/api/pid/configs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, gains: readPidFields() }),
      });
      const data = await res.json();
      if (data.ok) {
        setConfigStatus("Saved", "bg-success");
        refreshConfigList();
      } else {
        setConfigStatus(data.error || "Error", "bg-danger");
      }
    } catch (_) {
      setConfigStatus("Error", "bg-danger");
    }
  }

  async function loadConfig() {
    const select = document.getElementById("pid-config-select");
    const name = select ? select.value : "";
    if (!name) {
      setConfigStatus("Select", "bg-warning text-dark");
      return;
    }
    try {
      const res = await fetch("/api/pid/configs/" + encodeURIComponent(name));
      const data = await res.json();
      if (data.ok) {
        fillPidFields(data.gains);
        const nameEl = document.getElementById("pid-config-name");
        if (nameEl) nameEl.value = name;
        setConfigStatus("Loaded", "bg-success");
      } else {
        setConfigStatus(data.error || "Missing", "bg-danger");
      }
    } catch (_) {
      setConfigStatus("Error", "bg-danger");
    }
  }

  async function deleteConfig() {
    const select = document.getElementById("pid-config-select");
    const name = select ? select.value : "";
    if (!name) {
      setConfigStatus("Select", "bg-warning text-dark");
      return;
    }
    if (!window.confirm('Delete tune "' + name + '"?')) return;
    try {
      const res = await fetch("/api/pid/configs/" + encodeURIComponent(name), { method: "DELETE" });
      const data = await res.json();
      if (data.ok) {
        setConfigStatus("Deleted", "bg-success");
        refreshConfigList();
      } else {
        setConfigStatus(data.error || "Error", "bg-danger");
      }
    } catch (_) {
      setConfigStatus("Error", "bg-danger");
    }
  }

  function wireEvents() {
    document.querySelectorAll(".js-start-pid").forEach((btn) => btn.addEventListener("click", startPid));
    document.querySelectorAll(".js-zero-all-pid").forEach((btn) => btn.addEventListener("click", zeroAllPidAndThrusters));

    const btnEnable = document.getElementById("btn-enable");
    const btnDisable = document.getElementById("btn-disable");
    const btnResetAll = document.getElementById("btn-reset-all");
    if (btnEnable) btnEnable.addEventListener("click", enableOverride);
    if (btnDisable) btnDisable.addEventListener("click", disableOverride);
    if (btnResetAll) btnResetAll.addEventListener("click", () => AXES.forEach(resetSlider));

    AXES.forEach((axis) => {
      const slider = document.getElementById("slider-" + axis);
      if (!slider) return;
      slider.addEventListener("input", () => updateValueDisplay(axis));
      slider.addEventListener("dblclick", () => resetSlider(axis));
      updateValueDisplay(axis);
    });

    document.querySelectorAll(".js-use-current").forEach((btn) => {
      btn.addEventListener("click", () => {
        const axis = btn.dataset.axis;
        const el = document.getElementById("setpoint-" + axis);
        const value = Number(latestImu[axis]);
        if (el && Number.isFinite(value)) el.value = clampSetpoint(axis, value).toFixed(1);
      });
    });

    const btnSendSetpoints = document.getElementById("btn-send-setpoints");
    const btnClearSetpoints = document.getElementById("btn-clear-setpoints");
    if (btnSendSetpoints) btnSendSetpoints.addEventListener("click", sendSetpoints);
    if (btnClearSetpoints) btnClearSetpoints.addEventListener("click", clearSetpoints);

    const btnPidRequest = document.getElementById("btn-pid-request");
    const btnPidSend = document.getElementById("btn-pid-send");
    if (btnPidRequest) btnPidRequest.addEventListener("click", requestPidGains);
    if (btnPidSend) btnPidSend.addEventListener("click", sendPidGains);

    const btnFrameLock = document.getElementById("btn-frame-lock");
    const btnFrameUnlock = document.getElementById("btn-frame-unlock");
    if (btnFrameLock) btnFrameLock.addEventListener("click", () => sendFrameCommand("lock"));
    if (btnFrameUnlock) btnFrameUnlock.addEventListener("click", () => sendFrameCommand("unlock"));

    const btnPidSave = document.getElementById("btn-pid-save");
    const btnPidLoad = document.getElementById("btn-pid-load");
    const btnPidDelete = document.getElementById("btn-pid-delete");
    if (btnPidSave) btnPidSave.addEventListener("click", saveConfig);
    if (btnPidLoad) btnPidLoad.addEventListener("click", loadConfig);
    if (btnPidDelete) btnPidDelete.addEventListener("click", deleteConfig);
  }

  wireEvents();
  refreshConfigList();
  pollImuAndTelemetry();
  pollRovStatus();
  setInterval(pollImuAndTelemetry, 200);
  setInterval(pollRovStatus, 500);
})();
