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

    // ── Controller mapping ───────────────────────────────────
    const mappingContainer = document.getElementById("mapping-container");
    const mappingStatus = document.getElementById("mapping-status");
    let mappingMeta = {}; // action -> input type

    const ACTION_LABELS = {
      surge: "Surge (stick)", sway: "Sway (stick)", heave: "Heave (stick)", yaw: "Yaw (stick)",
      pitch: "Pitch (shift+stick)", roll: "Roll (shift+stick)",
      manip_pos: "Manip open", manip_neg: "Manip close",
      pitchroll_shift: "Pitch/Roll shift", dock: "Dock-hold toggle", frame: "Frame toggle",
    };

    function setMappingStatus(text) {
      if (!mappingStatus) return;
      mappingStatus.textContent = text;
      setTimeout(() => { if (mappingStatus.textContent === text) mappingStatus.textContent = ""; }, 2000);
    }

    function setField(action, which, value) {
      const id = "map-" + action + (which === "sdl" ? "-controller" : "-joystick");
      const el = document.getElementById(id);
      if (el) el.value = value;
    }

    function bindAction(action, btn) {
      const isButton = mappingMeta[action] === "button";
      const original = btn.textContent;
      btn.textContent = "Press…";
      btn.disabled = true;
      const deadline = Date.now() + 4000;
      const baseline = {};
      let captured = false;

      const finish = () => { btn.textContent = original; btn.disabled = false; };
      const poll = () => {
        fetch("/api/controller/live-input").then(r => r.json()).then(d => {
          if (!d.ok) return finish();
          const which = d.source === "sdl_gamecontroller" ? "sdl" : "raw";
          if (isButton) {
            (d.buttons || []).forEach((v, i) => {
              if (!captured && v > 0.5) { setField(action, which, i); captured = true; }
            });
          } else {
            const axesNow = d.axes || [];
            if (!Object.keys(baseline).length) axesNow.forEach((v, i) => { baseline[i] = v; });
            axesNow.forEach((v, i) => {
              if (!captured && Math.abs(v - (baseline[i] || 0)) > 0.5) { setField(action, which, i); captured = true; }
            });
          }
          if (captured || Date.now() > deadline) return finish();
          setTimeout(poll, 100);
        }).catch(finish);
      };
      poll();
    }

    function buildMappingRows(mapping) {
      if (!mappingContainer) return;
      mappingContainer.innerHTML = "";
      mappingMeta = {};
      Object.keys(mapping).forEach(action => {
        const entry = mapping[action];
        mappingMeta[action] = entry.type;
        const label = ACTION_LABELS[action] || action;
        const invertCell = entry.type === "axis"
          ? `<div class="col-auto" style="width:48px"><input class="form-check-input" type="checkbox" id="map-${action}-invert" ${entry.invert ? "checked" : ""}></div>`
          : `<div class="col-auto" style="width:48px"></div>`;
        const row = document.createElement("div");
        row.className = "row g-1 align-items-center mb-1";
        row.innerHTML =
          `<div class="col-4 small">${label}</div>` +
          `<div class="col-auto"><input type="number" class="form-control form-control-sm" id="map-${action}-controller" value="${entry.controller}" style="width:72px"></div>` +
          `<div class="col-auto"><input type="number" class="form-control form-control-sm" id="map-${action}-joystick" value="${entry.joystick}" style="width:72px"></div>` +
          invertCell +
          `<div class="col-auto"><button type="button" class="btn btn-sm btn-outline-info" data-action="${action}">Bind</button></div>`;
        mappingContainer.appendChild(row);
      });
      mappingContainer.querySelectorAll("button[data-action]").forEach(btn => {
        btn.addEventListener("click", () => bindAction(btn.dataset.action, btn));
      });
    }

    function collectMapping() {
      const mapping = {};
      Object.keys(mappingMeta).forEach(action => {
        const c = document.getElementById("map-" + action + "-controller");
        const j = document.getElementById("map-" + action + "-joystick");
        const inv = document.getElementById("map-" + action + "-invert");
        const entry = { controller: parseInt(c.value, 10), joystick: parseInt(j.value, 10) };
        if (inv) entry.invert = inv.checked;
        mapping[action] = entry;
      });
      return mapping;
    }

    if (mappingContainer) {
      fetch("/api/controller/mapping")
        .then(r => r.json())
        .then(d => { if (d.ok) buildMappingRows(d.mapping); })
        .catch(() => {});

      const saveBtn = document.getElementById("mapping-save");
      const resetBtn = document.getElementById("mapping-reset");
      if (saveBtn) saveBtn.addEventListener("click", () => {
        fetch("/api/controller/mapping", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ mapping: collectMapping() }),
        }).then(r => r.json()).then(d => {
          if (d.ok) { buildMappingRows(d.mapping); setMappingStatus("Saved"); }
          else setMappingStatus(d.error || "Error");
        }).catch(() => setMappingStatus("Error"));
      });
      if (resetBtn) resetBtn.addEventListener("click", () => {
        fetch("/api/controller/mapping/reset", { method: "POST" })
          .then(r => r.json()).then(d => { if (d.ok) { buildMappingRows(d.mapping); setMappingStatus("Reset"); } })
          .catch(() => setMappingStatus("Error"));
      });
    }
});
