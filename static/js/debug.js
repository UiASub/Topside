// debug.js – Debug slider page logic + IMU readout + offset controls
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
})();
