(function () {
  const feed = document.getElementById("ip-camera-feed");
  const state = document.getElementById("ip-camera-state");
  const activeIp = document.getElementById("ip-camera-active-ip");
  const activeUrl = document.getElementById("ip-camera-active-url");
  const ipInput = document.getElementById("ip-camera-ip");
  const nameInput = document.getElementById("ip-camera-name");
  const presetSelect = document.getElementById("ip-camera-presets");
  const feedback = document.getElementById("ip-camera-feedback");
  const btnApply = document.getElementById("ip-camera-apply");
  const btnSave = document.getElementById("ip-camera-save");
  const btnLoad = document.getElementById("ip-camera-load");
  const btnDelete = document.getElementById("ip-camera-delete");

  let presets = [];

  function setFeedback(text, cls) {
    if (!feedback) return;
    feedback.textContent = text;
    feedback.className = "small mt-2 " + cls;
  }

  function setState(status) {
    if (!state) return;
    if (status && status.connected) {
      state.textContent = "LIVE";
      state.className = "badge bg-success";
    } else {
      state.textContent = "OFFLINE";
      state.className = "badge bg-danger";
    }
  }

  function reloadFeed() {
    if (feed) feed.src = "/ip_video_feed?ts=" + Date.now();
  }

  function selectedPreset() {
    const name = presetSelect ? presetSelect.value : "";
    return presets.find((preset) => preset.name === name);
  }

  function renderPresets(list) {
    presets = Array.isArray(list) ? list : [];
    if (!presetSelect) return;
    presetSelect.innerHTML = "";
    if (presets.length === 0) {
      const opt = document.createElement("option");
      opt.value = "";
      opt.textContent = "No presets";
      presetSelect.appendChild(opt);
      return;
    }
    presets.forEach((preset) => {
      const opt = document.createElement("option");
      opt.value = preset.name;
      opt.textContent = preset.name + " - " + preset.ip;
      presetSelect.appendChild(opt);
    });
  }

  async function loadConfigs() {
    try {
      const res = await fetch("/api/ip_camera/configs", { cache: "no-store" });
      const data = await res.json();
      if (!data.ok) return;
      renderPresets(data.presets || []);
      if (activeIp) activeIp.textContent = data.active_ip || "--";
      if (activeUrl) activeUrl.textContent = data.active_url || "--";
      if (ipInput && data.active_ip) ipInput.value = data.active_ip;
      setState(data.status || {});
    } catch (error) {
      setFeedback("Failed to load camera config", "text-danger");
    }
  }

  async function savePreset() {
    const name = nameInput ? nameInput.value.trim() : "";
    const ip = ipInput ? ipInput.value.trim() : "";
    if (!name || !ip) {
      setFeedback("Enter preset name and IP.", "text-warning");
      return;
    }
    try {
      const res = await fetch("/api/ip_camera/configs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, ip }),
      });
      const data = await res.json();
      if (data.ok) {
        setFeedback("Preset saved.", "text-success");
        await loadConfigs();
        if (presetSelect) presetSelect.value = name;
      } else {
        setFeedback(data.error || "Save failed.", "text-danger");
      }
    } catch (error) {
      setFeedback("Save failed.", "text-danger");
    }
  }

  async function deletePreset() {
    const preset = selectedPreset();
    if (!preset) {
      setFeedback("Select a preset.", "text-warning");
      return;
    }
    try {
      const res = await fetch("/api/ip_camera/configs/" + encodeURIComponent(preset.name), { method: "DELETE" });
      const data = await res.json();
      if (data.ok) {
        setFeedback("Preset deleted.", "text-success");
        renderPresets(data.presets || []);
      } else {
        setFeedback(data.error || "Delete failed.", "text-danger");
      }
    } catch (error) {
      setFeedback("Delete failed.", "text-danger");
    }
  }

  function loadPreset() {
    const preset = selectedPreset();
    if (!preset) {
      setFeedback("Select a preset.", "text-warning");
      return;
    }
    if (nameInput) nameInput.value = preset.name;
    if (ipInput) ipInput.value = preset.ip;
    setFeedback("Preset loaded.", "text-light-muted");
  }

  async function applyIp() {
    const ip = ipInput ? ipInput.value.trim() : "";
    if (!ip) {
      setFeedback("Enter an IP address.", "text-warning");
      return;
    }
    if (btnApply) btnApply.disabled = true;
    setFeedback("Applying IP...", "text-warning");
    try {
      const res = await fetch("/api/ip_camera/reassign", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ip }),
      });
      const data = await res.json();
      if (data.ok) {
        if (activeIp) activeIp.textContent = data.active_ip || ip;
        if (activeUrl) activeUrl.textContent = data.active_url || "--";
        setState(data.status || {});
        reloadFeed();
        setFeedback("Camera reassigned.", "text-success");
      } else {
        setFeedback(data.error || "Apply failed.", "text-danger");
      }
    } catch (error) {
      setFeedback("Apply failed.", "text-danger");
    }
    if (btnApply) btnApply.disabled = false;
  }

  async function pollStatus() {
    try {
      const res = await fetch("/api/ip_camera/status", { cache: "no-store" });
      const data = await res.json();
      setState(data);
    } catch (_) {
      setState({ connected: false });
    }
  }

  if (btnSave) btnSave.addEventListener("click", savePreset);
  if (btnDelete) btnDelete.addEventListener("click", deletePreset);
  if (btnLoad) btnLoad.addEventListener("click", loadPreset);
  if (btnApply) btnApply.addEventListener("click", applyIp);

  loadConfigs();
  setInterval(pollStatus, 3000);
})();
