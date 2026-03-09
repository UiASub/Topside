document.addEventListener("DOMContentLoaded", function () {
    const slider = document.getElementById("update-interval");
    const intervalDisplay = document.getElementById("interval-value");

    // Start with the default update interval of 500ms
    let batteryInterval = setInterval(updateBattery, 500);
    let depthInterval = setInterval(updateDepth, 500);
    let lightsInterval = setInterval(updateLights, 500);
    let sensorsInterval = setInterval(updateSensors, 500);
    let thrustersInterval = setInterval(updateThrusterStatus, 500)

    slider.addEventListener("input", function () {
        const newInterval = parseInt(slider.value);
        intervalDisplay.textContent = newInterval;

        // Clear previous intervals
        clearInterval(batteryInterval);
        clearInterval(depthInterval);
        clearInterval(lightsInterval);
        clearInterval(sensorsInterval);
        clearInterval(thrustersInterval);

        // Set new intervals with the updated time
        batteryInterval = setInterval(updateBattery, newInterval);
        depthInterval = setInterval(updateDepth, newInterval);
        lightsInterval = setInterval(updateLights, newInterval);
        sensorsInterval = setInterval(updateSensors, newInterval);
        thrustersInterval = setInterval(updateThrusterStatus, newInterval);
    });

    // ── Gain sliders ────────────────────────────────────────
    const axes = ["surge", "sway", "heave", "roll", "pitch", "yaw"];
    const masterSlider = document.getElementById("gain-master");
    const masterDisplay = document.getElementById("gain-master-value");

    // Fetch current gains on load
    fetch("/api/controller/gains")
      .then(r => r.json())
      .then(data => {
        if (!data.ok) return;
        const g = data.gains;
        if (masterSlider) {
          masterSlider.value = g.master;
          masterDisplay.textContent = Number(g.master).toFixed(2);
        }
        axes.forEach(axis => {
          const sl = document.getElementById("gain-" + axis);
          const disp = document.getElementById("gain-" + axis + "-value");
          if (sl && g[axis] !== undefined) {
            sl.value = g[axis];
            disp.textContent = Number(g[axis]).toFixed(2);
          }
        });
      })
      .catch(() => {});

    function sendGains(payload) {
      fetch("/api/controller/gains", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }).catch(() => {});
    }

    // Master gain: also updates all per-axis sliders
    if (masterSlider) {
      masterSlider.addEventListener("input", function () {
        const val = parseFloat(this.value);
        masterDisplay.textContent = val.toFixed(2);
        // Set all per-axis sliders to the master value
        axes.forEach(axis => {
          const sl = document.getElementById("gain-" + axis);
          const disp = document.getElementById("gain-" + axis + "-value");
          if (sl) {
            sl.value = val;
            disp.textContent = val.toFixed(2);
          }
        });
        // Build full payload: master + all axes
        const payload = { master: val };
        axes.forEach(a => payload[a] = val);
        sendGains(payload);
      });
    }

    // Per-axis gain sliders
    axes.forEach(axis => {
      const sl = document.getElementById("gain-" + axis);
      if (!sl) return;
      sl.addEventListener("input", function () {
        const val = parseFloat(this.value);
        document.getElementById("gain-" + axis + "-value").textContent = val.toFixed(2);
        sendGains({ [axis]: val });
      });
    });
});
