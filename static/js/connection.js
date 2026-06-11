(function () {
  const badge = document.getElementById("nucleo-contact-badge");
  const lastAck = document.getElementById("nucleo-last-ack");
  const udpRx = document.getElementById("nucleo-udp-rx");
  const udpErrors = document.getElementById("nucleo-udp-errors");
  const details = document.getElementById("nucleo-link-details");
  const resetBtn = document.getElementById("btn-system-reset");
  const resetStatus = document.getElementById("system-reset-status");

  function fmt(value) {
    return value == null ? "--" : String(Math.round(value));
  }

  function setBadge(ackAge) {
    if (!badge) return;
    if (ackAge == null) {
      badge.textContent = "NO ACK";
      badge.className = "badge bg-secondary";
    } else if (ackAge < 1000) {
      badge.textContent = "LIVE";
      badge.className = "badge bg-success";
    } else if (ackAge < 3000) {
      badge.textContent = "STALE";
      badge.className = "badge bg-warning text-dark";
    } else {
      badge.textContent = "DEGRADED";
      badge.className = "badge bg-danger";
    }
  }

  async function pollConnection() {
    try {
      const res = await fetch("/api/command/status", { cache: "no-store" });
      const data = await res.json();
      if (!data.ok) return;

      const uplink = data.uplink || {};
      const ackAge = uplink.last_ack_age_ms;
      setBadge(ackAge);
      if (lastAck) lastAck.textContent = ackAge == null ? "--" : fmt(ackAge) + " ms";
      if (udpRx) udpRx.textContent = data.udp_rx_count == null ? "--" : String(data.udp_rx_count);
      if (udpErrors) udpErrors.textContent = data.udp_rx_errors == null ? "--" : String(data.udp_rx_errors);
      if (details) {
        details.textContent = JSON.stringify(
          {
            uplink,
            resource: {
              udp_rx_count: data.udp_rx_count,
              udp_rx_errors: data.udp_rx_errors,
            },
          },
          null,
          2
        );
      }
    } catch (_) {
      setBadge(null);
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
