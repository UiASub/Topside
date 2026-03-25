// debug.js – Debug slider page logic
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
