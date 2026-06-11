document.addEventListener("DOMContentLoaded", function () {
  const axes = ["surge", "sway", "heave", "roll", "pitch", "yaw"];
  const masterSlider = document.getElementById("gain-master");
  const masterDisplay = document.getElementById("gain-master-value");

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

  function sendGains(payload) {
    fetch("/api/controller/gains", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).catch(() => {});
  }

  fetch("/api/controller/gains")
    .then((r) => r.json())
    .then((data) => {
      if (!data.ok) return;
      const gains = data.gains;
      if (masterSlider && gains.master !== undefined) {
        masterSlider.value = gains.master;
        if (masterDisplay) masterDisplay.textContent = Number(gains.master).toFixed(2);
      }
      axes.forEach((axis) => {
        const slider = document.getElementById("gain-" + axis);
        if (!slider || gains[axis] === undefined) return;
        slider.value = gains[axis];
        setText("gain-" + axis + "-value", Number(gains[axis]).toFixed(2));
      });
    })
    .catch(() => {});

  if (masterSlider) {
    masterSlider.addEventListener("input", function () {
      const value = parseFloat(this.value);
      if (masterDisplay) masterDisplay.textContent = value.toFixed(2);
      const payload = { master: value };
      axes.forEach((axis) => {
        const slider = document.getElementById("gain-" + axis);
        if (slider) slider.value = value;
        setText("gain-" + axis + "-value", value.toFixed(2));
        payload[axis] = value;
      });
      sendGains(payload);
    });
  }

  axes.forEach((axis) => {
    const slider = document.getElementById("gain-" + axis);
    if (!slider) return;
    slider.addEventListener("input", function () {
      const value = parseFloat(this.value);
      setText("gain-" + axis + "-value", value.toFixed(2));
      sendGains({ [axis]: value });
    });
  });

  const axesYaw = document.getElementById("axes-yaw");
  const axesPitch = document.getElementById("axes-pitch");
  const axesRoll = document.getElementById("axes-roll");

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
        setFeedback("axes-feedback", data.ok ? "Mapping saved" : "Failed to save mapping", data.ok ? "text-success" : "text-danger");
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
        setFeedback("accel-feedback", data.ok ? "Accelerometer mapping saved" : "Failed to save mapping", data.ok ? "text-success" : "text-danger");
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
