(function () {
  const badge = document.getElementById("nucleo-contact-badge");
  const lastAck = document.getElementById("nucleo-last-ack");
  const bestProof = document.getElementById("nucleo-best-proof");
  const imuAge = document.getElementById("nucleo-imu-age");
  const proofBody = document.getElementById("nucleo-proof-body");
  const details = document.getElementById("nucleo-link-details");
  const resetBtn = document.getElementById("btn-system-reset");
  const resetStatus = document.getElementById("system-reset-status");

  function fmt(value) {
    return value == null ? "--" : String(Math.round(value));
  }

  function setBadge(connected, bestAgeMs) {
    if (!badge) return;
    if (!connected) {
      badge.textContent = "NO LIVE PROOF";
      badge.className = "badge bg-secondary";
    } else if (bestAgeMs != null && bestAgeMs < 1000) {
      badge.textContent = "LIVE";
      badge.className = "badge bg-success";
    } else if (bestAgeMs != null && bestAgeMs < 3000) {
      badge.textContent = "STALE";
      badge.className = "badge bg-warning text-dark";
    } else {
      badge.textContent = "LIVE, SLOW";
      badge.className = "badge bg-warning text-dark";
    }
  }

  function renderProofs(proofs) {
    if (!proofBody) return;
    const frag = document.createDocumentFragment();
    (proofs || []).forEach((proof) => {
      const tr = document.createElement("tr");
      const status = document.createElement("span");
      status.className = "badge " + (proof.active ? "bg-success" : "bg-secondary");
      status.textContent = proof.active ? "LIVE" : "STALE";
      [proof.name || "--", status, proof.age_ms == null ? "--" : fmt(proof.age_ms) + " ms", proof.detail || ""].forEach(
        (value) => {
          const td = document.createElement("td");
          if (value instanceof HTMLElement) td.appendChild(value);
          else td.textContent = value;
          tr.appendChild(td);
        }
      );
      frag.appendChild(tr);
    });
    proofBody.innerHTML = "";
    proofBody.appendChild(frag);
  }

  function minAge(proofs) {
    const liveAges = (proofs || [])
      .filter((proof) => proof.active && proof.age_ms != null)
      .map((proof) => Number(proof.age_ms))
      .filter((value) => Number.isFinite(value));
    return liveAges.length ? Math.min(...liveAges) : null;
  }

  async function pollConnection() {
    try {
      const res = await fetch("/api/connection/status", { cache: "no-store" });
      const data = await res.json();
      if (!data.ok) return;

      const uplink = data.uplink || {};
      const imu = data.imu || {};
      const bestAgeMs = minAge(data.proofs);
      setBadge(data.connected === true, bestAgeMs);
      renderProofs(data.proofs);
      if (bestProof) bestProof.textContent = bestAgeMs == null ? "--" : fmt(bestAgeMs) + " ms";
      if (lastAck) lastAck.textContent = uplink.last_ack_age_ms == null ? "--" : fmt(uplink.last_ack_age_ms) + " ms";
      if (imuAge) imuAge.textContent = imu.age_ms == null ? "--" : fmt(imu.age_ms) + " ms";
      if (details) {
        details.textContent = JSON.stringify(
          {
            uplink,
            resource: data.resource,
            imu: data.imu,
          },
          null,
          2
        );
      }
    } catch (_) {
      setBadge(false, null);
      if (details) details.textContent = "Connection status unavailable";
    }
  }

  if (resetBtn) {
    resetBtn.addEventListener("click", async function () {
      if (!window.confirm("Restart the MCU now?")) return;
      resetBtn.disabled = true;
      if (resetStatus) {
        resetStatus.textContent = "SENDING";
        resetStatus.className = "badge bg-warning text-dark";
      }
      try {
        const res = await fetch("/api/system/reset", { method: "POST" });
        const data = await res.json();
        if (resetStatus) {
          resetStatus.textContent = data.ok ? "RESET SENT" : data.error || "FAILED";
          resetStatus.className = "badge " + (data.ok ? "bg-success" : "bg-danger");
        }
      } catch (error) {
        if (resetStatus) {
          resetStatus.textContent = "ERROR";
          resetStatus.className = "badge bg-danger";
        }
      }
      setTimeout(() => {
        if (resetStatus) {
          resetStatus.textContent = "READY";
          resetStatus.className = "badge bg-secondary";
        }
        resetBtn.disabled = false;
      }, 3000);
    });
  }

  pollConnection();
  setInterval(pollConnection, 1000);
})();
