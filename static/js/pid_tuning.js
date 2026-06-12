// PID tuning page controls.
(function () {
  "use strict";

  const AXES = ["surge", "sway", "heave", "roll", "pitch", "yaw"];
  const ROT_AXES = ["roll", "pitch", "yaw"];
  const PID_GAINS = ["kp", "ki", "kd"];
  const SEND_INTERVAL_MS = 50;

  const attitudeLimits = window.pidTuningAttitudeLimits || { roll: 180, pitch: 90, yaw: 180 };
  let overrideActive = false;
  let sendTimer = null;
  let latestImu = {};
  let latestTelemetry = null;
  let latestControlState = {};
  const localSetpoints = { roll: NaN, pitch: NaN, yaw: NaN };

  const controlPathStatus = document.getElementById("control-path-status");
  const pidModeStatus = document.getElementById("pid-mode-status");
  const branchStatus = document.getElementById("pid-branch");
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

  function axisError(axis, setpoint, position) {
    if (!isFiniteNumber(setpoint) || !isFiniteNumber(position)) return NaN;
    if (axis === "pitch") return setpoint - position;
    return normalizeAngle(setpoint - position);
  }

  function setBadge(el, text, cls) {
    if (!el) return;
    el.textContent = text;
    el.className = "badge " + cls;
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

  function controlPathLabel(path, killed) {
    if (killed) return "Controls locked";
    if (path === "Override Controls") return "Override sliders";
    if (path === "PS4") return "PS4 Controller";
    return path || "PS4 Controller";
  }

  function setControlPathStatus(path, killed) {
    if (!controlPathStatus) return;
    controlPathStatus.textContent = controlPathLabel(path, killed);
    controlPathStatus.className = "pid-status-value " + (killed ? "text-danger" : path === "Override Controls" ? "text-warning" : "text-info");
  }

  function syncLocalSetpoints(setpoints, options) {
    const clearMissing = !options || options.clearMissing !== false;
    ROT_AXES.forEach((axis) => {
      const hasAxis = setpoints && Object.prototype.hasOwnProperty.call(setpoints, axis);
      const value = hasAxis ? Number(setpoints[axis]) : NaN;
      const el = document.getElementById("setpoint-" + axis);
      if (Number.isFinite(value)) {
        localSetpoints[axis] = value;
        if (el && document.activeElement !== el) el.value = value.toFixed(1);
      } else {
        localSetpoints[axis] = NaN;
        if (clearMissing && el && document.activeElement !== el) el.value = "";
      }
    });
  }

  function setControlsDisabled(killed) {
    document.querySelectorAll("#btn-toggle-pid, #btn-enable, #btn-send-setpoints, .js-clear-axis").forEach((el) => {
      el.disabled = killed;
    });
    const btnKill = document.getElementById("btn-killswitch");
    const btnRearm = document.getElementById("btn-rearm");
    if (btnKill) btnKill.disabled = killed;
    if (btnRearm) btnRearm.disabled = !killed;
  }

  function updatePidToggle(pidOn, killed) {
    const btn = document.getElementById("btn-toggle-pid");
    if (!btn) return;
    btn.textContent = pidOn ? "Stop PID" : "Start PID";
    btn.className = "btn pid-toggle-btn " + (pidOn ? "btn-success" : "btn-primary");
    btn.disabled = killed;
  }

  function updateControlBanner(state) {
    latestControlState = state || {};
    const killed = latestControlState.killed === true;
    const pidOn = latestControlState.pid_enabled === true;
    const path = latestControlState.control_path || "PS4";
    const setpoints = latestControlState.pid_setpoints || {};
    const hasSetpoints = ROT_AXES.some((axis) => Number.isFinite(Number(setpoints[axis])));
    syncLocalSetpoints(setpoints, { clearMissing: false });

    setControlPathStatus(path, killed);
    setBadge(pidModeStatus, pidOn ? "ON" : "OFF", pidOn ? "bg-success" : "bg-secondary");
    setSetpointStatus(pidOn ? "ACTIVE" : hasSetpoints ? "SAVED" : "IDLE", pidOn ? "bg-danger" : hasSetpoints ? "bg-info text-dark" : "bg-secondary");
    updatePidToggle(pidOn, killed);
    setControlsDisabled(killed);
    updateAxisReadouts();

    const overrideBadge = document.getElementById("debug-status");
    setBadge(overrideBadge, latestControlState.override_active ? "ACTIVE" : "INACTIVE", latestControlState.override_active ? "bg-danger" : "bg-secondary");
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
    const fromLocal = localSetpoints[axis];
    if (latestControlState.pid_enabled === true && Number.isFinite(fromTelemetry)) return fromTelemetry;
    if (Number.isFinite(fromLocal)) return fromLocal;
    return fromTelemetry;
  }

  function updateAxisReadouts() {
    ROT_AXES.forEach((axis) => {
      const setpoint = getTelemetrySetpoint(axis);
      const position = Number(latestImu[axis]);
      const error = axisError(axis, setpoint, position);
      const positionEl = document.getElementById("readout-" + axis + "-position");
      const setpointEl = document.getElementById("readout-" + axis + "-setpoint");
      const errorEl = document.getElementById("readout-" + axis + "-error");
      if (positionEl) positionEl.textContent = fmt(position, 2);
      if (setpointEl) setpointEl.textContent = fmt(setpoint, 2);
      if (errorEl) {
        errorEl.textContent = fmt(error, 2);
        errorEl.className = "pid-readout-number pid-readout-error";
        if (!isFiniteNumber(error)) errorEl.className = "pid-readout-number text-muted";
        else if (Math.abs(error) > 25) errorEl.className = "pid-readout-number text-danger";
        else if (Math.abs(error) > 10) errorEl.className = "pid-readout-number text-warning";
      }
    });
  }

  function updateTelemetryTable() {
    updateAxisReadouts();
    if (!telemetryBody) return;
    const frag = document.createDocumentFragment();
    ROT_AXES.forEach((axis) => {
      const setpoint = getTelemetrySetpoint(axis);
      const position = Number(latestImu[axis]);
      const error = axisError(axis, setpoint, position);
      const tr = document.createElement("tr");
      const tdAxis = document.createElement("td");
      const tdSet = document.createElement("td");
      const tdPos = document.createElement("td");
      const tdErr = document.createElement("td");
      tdAxis.textContent = axis.toUpperCase();
      tdSet.textContent = fmt(setpoint, 2);
      tdPos.textContent = fmt(position, 2);
      tdErr.textContent = fmt(error, 2);
      if (isFiniteNumber(error) && Math.abs(error) > 10) tdErr.className = "text-warning";
      if (isFiniteNumber(error) && Math.abs(error) > 25) tdErr.className = "text-danger";
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
    const results = await Promise.allSettled([imuReq, telemetryReq]);

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

    updateTelemetryTable();
  }

  async function pollControlState() {
    try {
      const res = await fetch("/api/control/state", { cache: "no-store" });
      const data = await res.json();
      if (data.ok) updateControlBanner(data.state || {});
    } catch (err) {
      console.debug("Control state polling failed:", err);
    }
  }

  async function loadGitBranch() {
    try {
      const res = await fetch("/api/system/git", { cache: "no-store" });
      const data = await res.json();
      if (branchStatus) branchStatus.textContent = data.ok && data.git ? data.git.branch : "--";
    } catch (_) {
      if (branchStatus) branchStatus.textContent = "--";
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
      const res = await fetch("/api/debug/override", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(getAllSliderValues()),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || data.ok === false) {
        resetOverrideUi();
        setFeedback(data.error || "Override blocked.", "text-danger");
        if (data.state) updateControlBanner(data.state);
      }
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

  function fillSetpointFields(setpoints) {
    syncLocalSetpoints(setpoints);
  }

  async function startPid(force) {
    setSetpointStatus("STARTING", "bg-warning text-dark");
    const toggleBtn = document.getElementById("btn-toggle-pid");
    if (toggleBtn) toggleBtn.disabled = true;
    try {
      const res = await fetch("/api/pid/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ force: force === true }),
      });
      const data = await res.json();
      if (data.ok) {
        fillSetpointFields(data.setpoints || {});
        if (data.state) updateControlBanner(data.state);
        setSetpointStatus("ACTIVE", "bg-danger");
        setFeedback("Started from current IMU attitude.", "text-success");
      } else if (res.status === 409 && data.force_supported) {
        const raw = data.sanity && data.sanity.raw ? JSON.stringify(data.sanity.raw) : "{}";
        const proceed = window.confirm(
          "IMU sanity check failed.\n\nReason: " +
            (data.error || "Unknown") +
            "\nRaw: " +
            raw +
            "\n\nCancel is recommended. Press OK to continue anyway."
        );
        if (proceed) await startPid(true);
      } else {
        setSetpointStatus("BLOCKED", "bg-danger");
        setFeedback(data.error || "Start failed.", "text-danger");
        if (data.state) updateControlBanner(data.state);
      }
    } catch (err) {
      setSetpointStatus("ERROR", "bg-danger");
      setFeedback("Error: " + err.message, "text-danger");
    } finally {
      if (toggleBtn) toggleBtn.disabled = false;
      setControlsDisabled(latestControlState.killed === true);
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
        if (data.control_state) updateControlBanner(data.control_state);
        const pidActive = data.pid_active === true || (data.control_state && data.control_state.pid_enabled === true);
        const text = Object.entries(data.sent || {}).map(([k, v]) => k + "=" + v.toFixed(1)).join(", ");
        setSetpointStatus(pidActive ? "ACTIVE" : "SAVED", pidActive ? "bg-danger" : "bg-info text-dark");
        setFeedback((pidActive ? "Updated active setpoints: " : "Saved setpoints: ") + text, "text-success");
      } else {
        setSetpointStatus("ERROR", "bg-danger");
        setFeedback(data.error || "Setpoint send failed.", "text-danger");
        if (data.state) updateControlBanner(data.state);
      }
    } catch (err) {
      setSetpointStatus("ERROR", "bg-danger");
      setFeedback("Error: " + err.message, "text-danger");
    }
  }

  async function stopPid(clearSaved) {
    const clear = clearSaved === true;
    try {
      const res = await fetch("/api/pid/stop", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ clear }),
      });
      const data = await res.json().catch(() => ({}));
      if (clear) syncLocalSetpoints({});
      else if (data.state && data.state.pid_setpoints) syncLocalSetpoints(data.state.pid_setpoints, { clearMissing: false });
      resetOverrideUi();
      if (data.state) updateControlBanner(data.state);
      setSetpointStatus(clear ? "IDLE" : "SAVED", clear ? "bg-secondary" : "bg-info text-dark");
      setFeedback(clear ? "Setpoints cleared." : "PID stopped. Setpoints kept.", "text-light");
    } catch (err) {
      setFeedback("Error: " + err.message, "text-danger");
    }
  }

  function clearSetpoints() {
    return stopPid(true);
  }

  async function clearAxis(axis) {
    try {
      const res = await fetch("/api/pid/setpoints/" + encodeURIComponent(axis), { method: "DELETE" });
      const data = await res.json();
      if (data.ok) {
        syncLocalSetpoints(data.remaining || {});
        if (data.control_state) updateControlBanner(data.control_state);
        setFeedback(axis + " setpoint cleared.", "text-success");
      } else {
        setFeedback(data.error || "Clear failed.", "text-danger");
      }
    } catch (err) {
      setFeedback("Error: " + err.message, "text-danger");
    }
  }

  async function killControls() {
    try {
      const res = await fetch("/api/control/killswitch", { method: "POST" });
      const data = await res.json();
      AXES.forEach(resetSlider);
      resetOverrideUi();
      syncLocalSetpoints({});
      if (data.state) updateControlBanner(data.state);
      setFeedback(res.ok ? "Controls killed." : data.error || "Killswitch failed.", res.ok ? "text-danger" : "text-warning");
    } catch (err) {
      setFeedback("Error: " + err.message, "text-danger");
    }
  }

  async function rearmControls() {
    try {
      const res = await fetch("/api/control/rearm", { method: "POST" });
      const data = await res.json();
      AXES.forEach(resetSlider);
      resetOverrideUi();
      syncLocalSetpoints({});
      if (data.state) updateControlBanner(data.state);
      setFeedback(res.ok ? "Controls re-armed." : data.error || "Re-arm failed.", res.ok ? "text-success" : "text-danger");
    } catch (err) {
      setFeedback("Error: " + err.message, "text-danger");
    }
  }

  async function pollRovStatus() {
    try {
      const res = await fetch("/api/rov/status");
      const data = await res.json();
      const control = data.control_state || latestControlState || {};
      const uplink = data.uplink || {};
      if (data.control_state) updateControlBanner(data.control_state);
      if (rovStatus) {
        rovStatus.textContent = JSON.stringify(
          {
            control_path: controlPathLabel(control.control_path, control.killed === true),
            pid_enabled: control.pid_enabled,
            active_setpoints: control.pid_setpoints,
            manual_command_before_pid: control.manual_command_before_pid,
            pid_output: latestTelemetry && latestTelemetry.output ? latestTelemetry.output : {},
            final_topside_command: data.command,
            raw_payload: uplink.last_packet_hex,
            timestamp: uplink.last_send_timestamp,
            sequence: uplink.sequence,
            link: {
              ack_age_ms: uplink.last_ack_age_ms,
              watchdog_resends: uplink.watchdog_resends,
            },
            telemetry: {
              sequence: latestTelemetry ? latestTelemetry.sequence : null,
              timestamp: latestTelemetry ? latestTelemetry.timestamp : null,
            },
            resource: data.resource,
          },
          null,
          2
        );
      }
    } catch (err) {
      if (rovStatus) rovStatus.textContent = "Error fetching status";
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
    const btnTogglePid = document.getElementById("btn-toggle-pid");
    if (btnTogglePid) {
      btnTogglePid.addEventListener("click", () => {
        if (latestControlState.pid_enabled === true) stopPid(false);
        else startPid();
      });
    }

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

    document.querySelectorAll(".js-clear-axis").forEach((btn) => {
      btn.addEventListener("click", () => clearAxis(btn.dataset.axis));
    });

    const btnKill = document.getElementById("btn-killswitch");
    const btnRearm = document.getElementById("btn-rearm");
    if (btnKill) btnKill.addEventListener("click", killControls);
    if (btnRearm) btnRearm.addEventListener("click", rearmControls);

    const btnPidRequest = document.getElementById("btn-pid-request");
    const btnPidSend = document.getElementById("btn-pid-send");
    if (btnPidRequest) btnPidRequest.addEventListener("click", requestPidGains);
    if (btnPidSend) btnPidSend.addEventListener("click", sendPidGains);

    const btnPidSave = document.getElementById("btn-pid-save");
    const btnPidLoad = document.getElementById("btn-pid-load");
    const btnPidDelete = document.getElementById("btn-pid-delete");
    if (btnPidSave) btnPidSave.addEventListener("click", saveConfig);
    if (btnPidLoad) btnPidLoad.addEventListener("click", loadConfig);
    if (btnPidDelete) btnPidDelete.addEventListener("click", deleteConfig);
  }

  wireEvents();
  refreshConfigList();
  loadGitBranch();
  pollControlState();
  pollImuAndTelemetry();
  pollRovStatus();
  setInterval(pollControlState, 500);
  setInterval(pollImuAndTelemetry, 200);
  setInterval(pollRovStatus, 500);
})();
