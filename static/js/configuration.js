document.addEventListener("DOMContentLoaded", function () {
  function setText(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
  }

  function setFeedback(id, text, cls) {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = text;
    el.className = "small mt-2 " + cls;
  }

  function setInlineFeedback(id, text, cls) {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = text;
    el.className = "small " + cls;
  }

  function clampGain(value) {
    const number = parseFloat(value);
    if (!Number.isFinite(number)) return 1;
    return Math.max(0, Math.min(1, number));
  }

  function gainPercent(value) {
    return Math.round(clampGain(value) * 100) + "%";
  }

  const axesYaw = document.getElementById("axes-yaw");
  const axesPitch = document.getElementById("axes-pitch");
  const axesRoll = document.getElementById("axes-roll");
  const pidRateRoll = document.getElementById("pid-rate-roll");
  const pidRatePitch = document.getElementById("pid-rate-pitch");
  const pidRateYaw = document.getElementById("pid-rate-yaw");
  const controllerGainMaster = document.getElementById("controller-gain-master");
  const controllerGainSliders = Array.from(document.querySelectorAll("[data-axis].controller-gain-slider"));
  let controllerGainSaveTimer = null;

  function setGainBadge(text, cls) {
    const badge = document.getElementById("controller-gain-status");
    if (!badge) return;
    badge.textContent = text;
    badge.className = "badge " + cls;
  }

  function updateGainLabels() {
    const masterValue = document.getElementById("controller-gain-master-value");
    if (masterValue && controllerGainMaster) masterValue.textContent = gainPercent(controllerGainMaster.value);
    controllerGainSliders.forEach((slider) => {
      const value = document.getElementById(slider.id + "-value");
      if (value) value.textContent = gainPercent(slider.value);
    });
  }

  function readControllerGains() {
    const axes = {};
    controllerGainSliders.forEach((slider) => {
      axes[slider.dataset.axis] = clampGain(slider.value);
    });
    return {
      master: controllerGainMaster ? clampGain(controllerGainMaster.value) : 1,
      axes: axes,
    };
  }

  function fillControllerGains(gains) {
    const safe = gains || {};
    const axes = safe.axes || {};
    if (controllerGainMaster) controllerGainMaster.value = clampGain(safe.master == null ? 1 : safe.master);
    controllerGainSliders.forEach((slider) => {
      const axis = slider.dataset.axis;
      slider.value = clampGain(axes[axis] == null ? 1 : axes[axis]);
    });
    updateGainLabels();
  }

  async function saveControllerGains() {
    try {
      setGainBadge("SAVING", "bg-warning text-dark");
      const res = await fetch("/api/controller/gains", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(readControllerGains()),
      });
      const data = await res.json();
      if (data.ok && data.gains) {
        fillControllerGains(data.gains);
        setGainBadge("SAVED", "bg-success");
        setInlineFeedback("controller-gain-feedback", "Controller gain saved", "text-success");
      } else {
        setGainBadge("ERROR", "bg-danger");
        setInlineFeedback("controller-gain-feedback", "Failed to save controller gain", "text-danger");
      }
    } catch (error) {
      setGainBadge("ERROR", "bg-danger");
      setInlineFeedback("controller-gain-feedback", "Error: " + error.message, "text-danger");
    }
  }

  function queueControllerGainSave() {
    updateGainLabels();
    setGainBadge("CHANGED", "bg-info text-dark");
    setInlineFeedback("controller-gain-feedback", "Saving...", "text-light-muted");
    clearTimeout(controllerGainSaveTimer);
    controllerGainSaveTimer = setTimeout(saveControllerGains, 250);
  }

  fetch("/api/controller/gains")
    .then((r) => r.json())
    .then((data) => {
      if (!data.ok || !data.gains) return;
      fillControllerGains(data.gains);
      setGainBadge("READY", "bg-success");
    })
    .catch(() => {
      setGainBadge("ERROR", "bg-danger");
    });

  [controllerGainMaster].concat(controllerGainSliders).forEach((slider) => {
    if (!slider) return;
    slider.addEventListener("input", queueControllerGainSave);
    slider.addEventListener("change", queueControllerGainSave);
  });

  const resetControllerGains = document.getElementById("btn-reset-controller-gains");
  if (resetControllerGains) {
    resetControllerGains.addEventListener("click", function () {
      fillControllerGains({
        master: 1,
        axes: { surge: 1, sway: 1, heave: 1, roll: 1, pitch: 1, yaw: 1 },
      });
      saveControllerGains();
    });
  }

  fetch("/api/pid/rates")
    .then((r) => r.json())
    .then((data) => {
      if (!data.ok || !data.rates) return;
      if (pidRateRoll) pidRateRoll.value = data.rates.roll;
      if (pidRatePitch) pidRatePitch.value = data.rates.pitch;
      if (pidRateYaw) pidRateYaw.value = data.rates.yaw;
    })
    .catch(() => {});

  const savePidRates = document.getElementById("btn-save-pid-rates");
  if (savePidRates) {
    savePidRates.addEventListener("click", async function () {
      try {
        const res = await fetch("/api/pid/rates", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            roll: parseFloat(pidRateRoll.value) || 0,
            pitch: parseFloat(pidRatePitch.value) || 0,
            yaw: parseFloat(pidRateYaw.value) || 0,
          }),
        });
        const data = await res.json();
        if (data.ok && data.rates) {
          pidRateRoll.value = data.rates.roll;
          pidRatePitch.value = data.rates.pitch;
          pidRateYaw.value = data.rates.yaw;
          setFeedback("pid-rates-feedback", "Rates saved", "text-success");
        } else {
          setFeedback("pid-rates-feedback", "Failed to save rates", "text-danger");
        }
      } catch (error) {
        setFeedback("pid-rates-feedback", "Error: " + error.message, "text-danger");
      }
    });
  }

  fetch("/api/imu/axes")
    .then((r) => r.json())
    .then((data) => {
      if (!data.ok || !data.axes) return;
      if (axesYaw) axesYaw.value = data.axes.yaw;
      if (axesPitch) axesPitch.value = data.axes.pitch;
      if (axesRoll) axesRoll.value = data.axes.roll;
    })
    .catch(() => {});

  const saveAxes = document.getElementById("btn-save-axes");
  if (saveAxes) {
    saveAxes.addEventListener("click", async function () {
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
        const data = await res.json();
        setFeedback(
          "axes-feedback",
          data.ok ? "Mapping saved" : "Failed to save mapping",
          data.ok ? "text-success" : "text-danger"
        );
      } catch (error) {
        setFeedback("axes-feedback", "Error: " + error.message, "text-danger");
      }
    });
  }

  const accelX = document.getElementById("accel-x");
  const accelY = document.getElementById("accel-y");
  const accelZ = document.getElementById("accel-z");

  fetch("/api/imu/accel_axes")
    .then((r) => r.json())
    .then((data) => {
      if (!data.ok || !data.accel_axes) return;
      if (accelX) accelX.value = data.accel_axes.x;
      if (accelY) accelY.value = data.accel_axes.y;
      if (accelZ) accelZ.value = data.accel_axes.z;
    })
    .catch(() => {});

  const saveAccel = document.getElementById("btn-save-accel");
  if (saveAccel) {
    saveAccel.addEventListener("click", async function () {
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
        const data = await res.json();
        setFeedback(
          "accel-feedback",
          data.ok ? "Accelerometer mapping saved" : "Failed to save mapping",
          data.ok ? "text-success" : "text-danger"
        );
      } catch (error) {
        setFeedback("accel-feedback", "Error: " + error.message, "text-danger");
      }
    });
  }

  const offsetX = document.getElementById("offset-x");
  const offsetY = document.getElementById("offset-y");
  const offsetZ = document.getElementById("offset-z");

  fetch("/api/imu/offset")
    .then((r) => r.json())
    .then((data) => {
      if (!data.ok || !data.offset) return;
      if (offsetX) offsetX.value = data.offset.x;
      if (offsetY) offsetY.value = data.offset.y;
      if (offsetZ) offsetZ.value = data.offset.z;
    })
    .catch(() => {});

  const saveOffset = document.getElementById("btn-save-offset");
  if (saveOffset) {
    saveOffset.addEventListener("click", async function () {
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
        const data = await res.json();
        if (data.ok) {
          setFeedback("offset-feedback", "Offset saved", "text-success");
        } else {
          setFeedback("offset-feedback", "Failed to save offset", "text-danger");
        }
      } catch (error) {
        setFeedback("offset-feedback", "Error: " + error.message, "text-danger");
      }
    });
  }

  async function pollInputSource() {
    try {
      const res = await fetch("/api/command/status", { cache: "no-store" });
      const data = await res.json();
      if (!data.ok) return;

      const controller = data.controller || {};
      const override = data.override || {};
      const uplink = data.uplink || {};
      const connected = controller.connected === true || controller.active === true;
      const activeOverride = override.active === true;
      const ackAge = uplink.last_ack_age_ms;

      setText("input-controller", connected ? "Connected" : "Not active");
      setText("input-override", activeOverride ? "Active" : "Inactive");
      setText("input-last-ack", ackAge == null ? "--" : Math.round(ackAge) + " ms");

      const badge = document.getElementById("input-source-status");
      if (!badge) return;
      badge.textContent = activeOverride ? "OVERRIDE" : connected ? "CONTROLLER" : "IDLE";
      badge.className = "badge " + (activeOverride ? "bg-danger" : connected ? "bg-success" : "bg-secondary");
    } catch (_) {
      setText("input-controller", "Unavailable");
    }
  }

  pollInputSource();
  setInterval(pollInputSource, 1000);
});
