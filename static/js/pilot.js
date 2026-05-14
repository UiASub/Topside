/* ===================================================================
   Pilot HUD – JavaScript
   Fetches telemetry from existing APIs and updates the HUD elements
   =================================================================== */

(function () {
  "use strict";

  const camera = {
    img: null,
    shell: null,
    status: null,
    stateText: null,
    reconnectBtn: null,
    fitBtn: null,
    reconnectTimer: null,
    reconnectDelayMs: 1200,
    maxReconnectDelayMs: 8000,
    loadedOnce: false,
    fitContain: false,
  };

  function setCameraState(state, label) {
    if (!camera.status || !camera.stateText) return;
    camera.status.classList.remove("state-ok", "state-reconnecting", "state-waiting", "state-error");
    camera.status.classList.add(`state-${state}`);
    camera.stateText.textContent = label;
  }

  function cameraUrl() {
    return `/ip_video_feed?ts=${Date.now()}`;
  }

  function scheduleCameraReconnect(reason = "Reconnecting…") {
    if (!camera.img || camera.reconnectTimer) return;
    setCameraState("reconnecting", reason);
    camera.reconnectTimer = setTimeout(() => {
      camera.reconnectTimer = null;
      camera.img.src = cameraUrl();
      camera.reconnectDelayMs = Math.min(camera.reconnectDelayMs * 1.5, camera.maxReconnectDelayMs);
    }, camera.reconnectDelayMs);
  }

  function resetCameraReconnectBackoff() {
    camera.reconnectDelayMs = 1200;
    if (camera.reconnectTimer) {
      clearTimeout(camera.reconnectTimer);
      camera.reconnectTimer = null;
    }
  }

  function setFitMode(contain) {
    if (!camera.shell || !camera.fitBtn) return;
    camera.fitContain = contain;
    camera.shell.classList.toggle("fit-contain", contain);
    camera.shell.classList.toggle("fit-cover", !contain);
    camera.fitBtn.textContent = contain ? "Fill" : "Fit";
  }

  // ── Mission timer ─────────────────────────────────────────────
  const startTime = Date.now();
  function updateMissionTime() {
    const elapsed = Math.floor((Date.now() - startTime) / 1000);
    const h = String(Math.floor(elapsed / 3600)).padStart(2, "0");
    const m = String(Math.floor((elapsed % 3600) / 60)).padStart(2, "0");
    const s = String(elapsed % 60).padStart(2, "0");
    const el = document.getElementById("hud-mission-time");
    if (el) el.textContent = `${h}:${m}:${s}`;
  }

  // ── Compass strip builder ─────────────────────────────────────
  function buildCompassStrip() {
    const strip = document.getElementById("hud-compass-strip");
    if (!strip) return;
    strip.innerHTML = "";
    const cardinals = { 0: "N", 45: "NE", 90: "E", 135: "SE", 180: "S", 225: "SW", 270: "W", 315: "NW", 360: "N" };
    // Build from -90 to 450 for wrapping
    for (let deg = -90; deg <= 450; deg += 5) {
      const tick = document.createElement("div");
      tick.className = "compass-tick";
      const line = document.createElement("div");
      const normDeg = ((deg % 360) + 360) % 360;
      if (normDeg % 45 === 0) {
        line.className = "compass-tick-line major";
        const lbl = document.createElement("div");
        lbl.className = "compass-tick-label";
        lbl.textContent = cardinals[normDeg] || `${normDeg}`;
        tick.appendChild(line);
        tick.appendChild(lbl);
      } else if (normDeg % 10 === 0) {
        line.className = "compass-tick-line minor";
        tick.appendChild(line);
      } else {
        line.className = "compass-tick-line minor";
        line.style.height = "3px";
        tick.appendChild(line);
      }
      tick.dataset.deg = deg;
      strip.appendChild(tick);
    }
  }

  function updateCompass(heading) {
    const strip = document.getElementById("hud-compass-strip");
    if (!strip) return;
    // Each tick is 30px wide, ticks every 5°  →  6px per degree
    const offset = heading * 6;
    // Center the -90 start offset
    const baseOffset = -90 * 6;
    strip.style.transform = `translateX(${-(offset - baseOffset)}px)`;
  }

  // ── Artificial horizon ────────────────────────────────────────
  function updateHorizon(roll, pitch) {
    const svg = document.getElementById("hud-horizon");
    if (!svg) return;

    const sky    = document.getElementById("horizon-sky");
    const ground = document.getElementById("horizon-ground");
    const line   = document.getElementById("horizon-line");
    const pitchG = document.getElementById("horizon-pitch-group");

    // Pitch: 1px per degree, clamped to ±45
    const pitchPx = Math.max(-45, Math.min(45, pitch)) * 1.0;

    // Apply rotation (roll) and translation (pitch) to sky/ground group
    const transform = `rotate(${-roll}, 60, 60) translate(0, ${pitchPx})`;
    sky.setAttribute("transform", transform);
    ground.setAttribute("transform", transform);
    line.setAttribute("transform", transform);
    if (pitchG) pitchG.setAttribute("transform", transform);
  }

  function fmtAngle(v) {
    return (v >= 0 ? "+" : "") + v.toFixed(1) + "\u00B0";
  }

  // ── Data fetchers ─────────────────────────────────────────────

  async function fetchDepth() {
    try {
      const res = await fetch("/api/depth");
      const d = await res.json();
      const el = document.getElementById("hud-depth");
      const tgt = document.getElementById("hud-depth-target");
      if (el) el.textContent = d.dpt != null ? parseFloat(d.dpt).toFixed(1) : "--.-";
      if (tgt) tgt.textContent = d.dptSet != null ? parseFloat(d.dptSet).toFixed(1) : "--.-";
    } catch (_) { /* silent */ }
  }

  async function fetchBattery() {
    try {
      const res = await fetch("/api/battery");
      const d = await res.json();
      const level = d.battery ?? 0;
      const el = document.getElementById("hud-battery");
      const fill = document.getElementById("hud-battery-fill");
      if (el) el.textContent = level;
      if (fill) {
        fill.style.width = level + "%";
        fill.classList.remove("batt-low", "batt-mid");
        if (level < 20)      fill.classList.add("batt-low");
        else if (level < 50) fill.classList.add("batt-mid");
      }
    } catch (_) { /* silent */ }
  }

  async function fetchSensors() {
    try {
      const res = await fetch("/api/sensors");
      const d = await res.json();

      // VN-100S provides fused yaw/pitch/roll directly
      const angles = {
        roll:  d.roll  || 0,
        pitch: d.pitch || 0,
        yaw:   d.yaw   || 0,
      };

      // Update readouts
      const elRoll  = document.getElementById("hud-roll");
      const elPitch = document.getElementById("hud-pitch");
      const elHdg   = document.getElementById("hud-heading");
      if (elRoll)  elRoll.textContent  = fmtAngle(angles.roll);
      if (elPitch) elPitch.textContent = fmtAngle(angles.pitch);

      // Heading (yaw mapped to 0-360)
      const heading = ((angles.yaw % 360) + 360) % 360;
      if (elHdg) elHdg.textContent = heading.toFixed(0).padStart(3, "0");
      updateCompass(heading);
      updateHorizon(angles.roll, angles.pitch);
    } catch (_) { /* silent */ }
  }

  function setTelem(id, val) {
    const el = document.getElementById(id);
    if (el) el.textContent = val != null ? parseFloat(val).toFixed(2) : "—";
  }

  async function fetchThrusters() {
    try {
      const res = await fetch("/api/thrusters");
      const data = await res.json();
      const container = document.getElementById("hud-thrusters");
      if (!container) return;

      // Build thruster indicators if empty
      const thrusters = Array.isArray(data) ? data : Object.values(data);
      if (container.children.length === 0 && thrusters.length > 0) {
        container.innerHTML = "";
        thrusters.forEach((_, i) => {
          const item = document.createElement("div");
          item.className = "hud-thr-item";
          item.innerHTML = `
            <div class="hud-thr-dot" id="thr-dot-${i}"></div>
            <span class="hud-thr-label">T${i + 1}</span>
            <span class="hud-thr-val" id="thr-val-${i}">—</span>`;
          container.appendChild(item);
        });
      }

      thrusters.forEach((t, i) => {
        const dot = document.getElementById(`thr-dot-${i}`);
        const val = document.getElementById(`thr-val-${i}`);
        const power = t.power ?? t.pwr ?? 0;
        const temp  = t.temperature ?? t.temp ?? 0;

        if (val) val.textContent = `${power}W`;
        if (dot) {
          dot.classList.remove("thr-ok", "thr-warn", "thr-error");
          if (temp > 60)      dot.classList.add("thr-error");
          else if (temp > 40) dot.classList.add("thr-warn");
          else                dot.classList.add("thr-ok");
        }
      });
    } catch (_) { /* silent */ }
  }

  async function fetchLights() {
    try {
      const res = await fetch("/api/lights");
      const d = await res.json();
      const el = document.getElementById("hud-lights");
      if (el) {
        const level = d.level ?? d.light ?? d.value ?? "—";
        el.textContent = typeof level === "number" ? `${level}%` : level;
      }
    } catch (_) { /* silent */ }
  }

  async function fetchCameraStatus() {
    try {
      const res = await fetch("/api/ip_camera/status");
      const d = await res.json();
      const dot = document.getElementById("hud-rpi-dot");
      if (dot) {
        dot.classList.remove("status-ok", "status-err");
        dot.classList.add(d.connected ? "status-ok" : "status-err");
      }

      if (d.connected) {
        if (camera.loadedOnce) {
          setCameraState("ok", "Live");
          resetCameraReconnectBackoff();
        } else {
          setCameraState("waiting", "Waiting for first frame…");
        }
      } else {
        setCameraState("error", "Camera offline");
        scheduleCameraReconnect("Camera offline – reconnecting…");
      }
    } catch (_) { /* silent */ }
  }

  function initCameraFeed() {
    camera.img = document.getElementById("pilot-camera");
    camera.shell = document.getElementById("pilot-feed-shell");
    camera.status = document.getElementById("pilot-feed-status");
    camera.stateText = document.getElementById("pilot-feed-state");
    camera.reconnectBtn = document.getElementById("pilot-reconnect");
    camera.fitBtn = document.getElementById("pilot-fit");

    if (!camera.img) return;

    setCameraState("waiting", "Connecting…");

    camera.img.addEventListener("load", () => {
      camera.loadedOnce = true;
      setCameraState("ok", "Live");
      resetCameraReconnectBackoff();
    });

    camera.img.addEventListener("error", () => {
      setCameraState("error", "Stream error");
      scheduleCameraReconnect("Stream error – reconnecting…");
    });

    if (camera.reconnectBtn) {
      camera.reconnectBtn.addEventListener("click", () => {
        resetCameraReconnectBackoff();
        setCameraState("reconnecting", "Manual reconnect…");
        camera.img.src = cameraUrl();
      });
    }

    if (camera.fitBtn) {
      camera.fitBtn.addEventListener("click", () => setFitMode(!camera.fitContain));
    }

    setFitMode(false);
  }

  // ── Initialization ────────────────────────────────────────────
  function init() {
    buildCompassStrip();
    initCameraFeed();

    // Hide the page header/footer for immersive view
    const header = document.querySelector("header.header");
    if (header) header.style.display = "none";
    const footer = document.querySelector("footer.footer, .footer");
    if (footer) footer.style.display = "none";

    // Start polling loops  (keep rates low to avoid starving the MJPEG stream)
    setInterval(fetchDepth, 1000);
    setInterval(fetchBattery, 3000);
    setInterval(fetchSensors, 500);        // lower API pressure; keep camera smooth
    setInterval(fetchThrusters, 2000);
    setInterval(fetchLights, 3000);
    setInterval(fetchCameraStatus, 5000);
    setInterval(updateMissionTime, 1000);

    // Initial fetches
    fetchDepth();
    fetchBattery();
    fetchSensors();
    fetchThrusters();
    fetchLights();
    fetchCameraStatus();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
