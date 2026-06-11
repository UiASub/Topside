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

  const aruco = {
    enabled: false,
    state: null,
    toggleBtn: null,
    clearBtn: null,
    visible: null,
    log: null,
  };

  let hudLightSlider = null;
  let hudLightPostTimer = null;
  const startTime = Date.now();

  function setCameraState(state, label) {
    if (!camera.status || !camera.stateText) return;
    camera.status.classList.remove("state-ok", "state-reconnecting", "state-waiting", "state-error");
    camera.status.classList.add("state-" + state);
    camera.stateText.textContent = label;
  }

  function cameraUrl() {
    return "/ip_video_feed?ts=" + Date.now();
  }

  function scheduleCameraReconnect(label) {
    if (!camera.img || camera.reconnectTimer) return;
    setCameraState("reconnecting", label || "Reconnecting...");
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

  function updateMissionTime() {
    const elapsed = Math.floor((Date.now() - startTime) / 1000);
    const h = String(Math.floor(elapsed / 3600)).padStart(2, "0");
    const m = String(Math.floor((elapsed % 3600) / 60)).padStart(2, "0");
    const s = String(elapsed % 60).padStart(2, "0");
    const el = document.getElementById("hud-mission-time");
    if (el) el.textContent = `${h}:${m}:${s}`;
  }

  async function fetchDepth() {
    try {
      const res = await fetch("/api/depth");
      const data = await res.json();
      const depth = document.getElementById("hud-depth");
      const target = document.getElementById("hud-depth-target");
      if (depth) depth.textContent = data.dpt != null ? parseFloat(data.dpt).toFixed(1) : "--.-";
      if (target) target.textContent = data.dptSet != null ? parseFloat(data.dptSet).toFixed(1) : "--.-";
    } catch (_) {}
  }

  async function fetchLights() {
    try {
      const res = await fetch("/api/lights");
      const data = await res.json();
      const level = data.level ?? data.light ?? 0;
      const readout = document.getElementById("hud-lights");
      if (readout) readout.textContent = typeof level === "number" ? `${level}%` : String(level);
      if (hudLightSlider && document.activeElement !== hudLightSlider) {
        hudLightSlider.value = typeof level === "number" ? level : 0;
      }
    } catch (_) {}
  }

  async function postLights(level) {
    try {
      await fetch("/api/lights", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ level }),
      });
    } catch (_) {}
  }

  function queueLightPost(level) {
    if (hudLightPostTimer) return;
    hudLightPostTimer = setTimeout(() => {
      hudLightPostTimer = null;
    }, 100);
    postLights(level);
  }

  function initLightControls() {
    hudLightSlider = document.getElementById("hud-light-slider");
    if (!hudLightSlider) return;
    hudLightSlider.addEventListener("input", () => {
      const level = parseInt(hudLightSlider.value, 10);
      const readout = document.getElementById("hud-lights");
      if (readout) readout.textContent = `${level}%`;
      queueLightPost(level);
    });
    hudLightSlider.addEventListener("change", () => {
      postLights(parseInt(hudLightSlider.value, 10));
    });
  }

  async function fetchCameraStatus() {
    try {
      const res = await fetch("/api/ip_camera/status");
      const data = await res.json();
      const dot = document.getElementById("hud-rpi-dot");
      if (dot) {
        dot.classList.remove("status-ok", "status-err");
        dot.classList.add(data.connected ? "status-ok" : "status-err");
      }

      if (data.connected) {
        if (camera.loadedOnce) {
          setCameraState("ok", "Live");
          resetCameraReconnectBackoff();
        } else {
          setCameraState("waiting", "Waiting for first frame...");
        }
      } else {
        setCameraState("error", "Camera offline");
        scheduleCameraReconnect("Camera offline - reconnecting...");
      }
    } catch (_) {}
  }

  function renderArucoLog(log) {
    aruco.enabled = Boolean(log && log.enabled);
    if (aruco.state) {
      aruco.state.textContent = aruco.enabled ? "ON" : "OFF";
      aruco.state.classList.toggle("is-on", aruco.enabled);
    }
    if (aruco.toggleBtn) aruco.toggleBtn.textContent = aruco.enabled ? "Stop" : "Start";
    if (aruco.visible) {
      const visibleIds = log && Array.isArray(log.visible_ids) ? log.visible_ids : [];
      aruco.visible.textContent = visibleIds.length > 0 ? visibleIds.join(", ") : "--";
    }
    if (aruco.log) {
      const entries = log && Array.isArray(log.entries) ? log.entries : [];
      aruco.log.innerHTML = "";
      entries.forEach((entry) => {
        const item = document.createElement("li");
        item.textContent = "ID " + entry.id;
        aruco.log.appendChild(item);
      });
    }
  }

  async function fetchArucoLog() {
    try {
      const res = await fetch("/api/aruco-log");
      const data = await res.json();
      if (data.ok) renderArucoLog(data.log);
    } catch (_) {}
  }

  async function postArucoAction(action) {
    try {
      const res = await fetch("/api/aruco-log/" + action, { method: "POST" });
      const data = await res.json();
      if (data.ok) renderArucoLog(data.log);
    } catch (_) {}
  }

  function initArucoControls() {
    aruco.state = document.getElementById("hud-aruco-state");
    aruco.toggleBtn = document.getElementById("hud-aruco-toggle");
    aruco.clearBtn = document.getElementById("hud-aruco-clear");
    aruco.visible = document.getElementById("hud-aruco-visible");
    aruco.log = document.getElementById("hud-aruco-log");

    if (aruco.toggleBtn) {
      aruco.toggleBtn.addEventListener("click", () => {
        postArucoAction(aruco.enabled ? "stop" : "start");
      });
    }
    if (aruco.clearBtn) aruco.clearBtn.addEventListener("click", () => postArucoAction("clear"));
  }

  function initCameraFeed() {
    camera.img = document.getElementById("pilot-camera");
    camera.shell = document.getElementById("pilot-feed-shell");
    camera.status = document.getElementById("pilot-feed-status");
    camera.stateText = document.getElementById("pilot-feed-state");
    camera.reconnectBtn = document.getElementById("pilot-reconnect");
    camera.fitBtn = document.getElementById("pilot-fit");

    if (!camera.img) return;
    setCameraState("waiting", "Connecting...");

    camera.img.addEventListener("load", () => {
      camera.loadedOnce = true;
      setCameraState("ok", "Live");
      resetCameraReconnectBackoff();
    });
    camera.img.addEventListener("error", () => {
      setCameraState("error", "Stream error");
      scheduleCameraReconnect("Stream error - reconnecting...");
    });
    if (camera.reconnectBtn) {
      camera.reconnectBtn.addEventListener("click", () => {
        resetCameraReconnectBackoff();
        setCameraState("reconnecting", "Manual reconnect...");
        camera.img.src = cameraUrl();
      });
    }
    if (camera.fitBtn) camera.fitBtn.addEventListener("click", () => setFitMode(!camera.fitContain));
    setFitMode(false);
  }

  function init() {
    initCameraFeed();
    initArucoControls();
    initLightControls();

    const header = document.querySelector("header.header");
    if (header) header.style.display = "none";
    const footer = document.querySelector("footer.footer, .footer");
    if (footer) footer.style.display = "none";

    fetchDepth();
    fetchLights();
    fetchCameraStatus();
    fetchArucoLog();
    updateMissionTime();

    setInterval(fetchDepth, 1000);
    setInterval(fetchLights, 3000);
    setInterval(fetchCameraStatus, 5000);
    setInterval(fetchArucoLog, 1000);
    setInterval(updateMissionTime, 1000);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
