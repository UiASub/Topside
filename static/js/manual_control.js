// Manual Control — sliders that POST to /api/rov/command
(function () {
  const SEND_INTERVAL = 100; // ms between sends (~10 Hz)
  let dirty = false;

  const sliders = document.querySelectorAll('[data-axis]');
  const statusBadge = document.getElementById('mc-status');
  const resetBtn = document.getElementById('mc-reset');

  // Update label + mark dirty on every slider move
  sliders.forEach(slider => {
    slider.addEventListener('input', () => {
      const axis = slider.dataset.axis;
      const normalized = axis === 'light'
        ? (slider.value / 100).toFixed(2)
        : (slider.value / 100).toFixed(2);
      document.getElementById(`mc-val-${axis}`).textContent = normalized;
      dirty = true;
    });
  });

  // Reset all sliders to zero
  resetBtn.addEventListener('click', () => {
    sliders.forEach(s => {
      s.value = 0;
      const axis = s.dataset.axis;
      document.getElementById(`mc-val-${axis}`).textContent = '0.00';
    });
    dirty = true; // send zeroes
  });

  // Periodically send current slider state
  setInterval(async () => {
    if (!dirty) return;
    dirty = false;

    const axes = {};
    sliders.forEach(s => {
      axes[s.dataset.axis] = s.value / 100; // normalize to -1..1 (or 0..1 for light)
    });

    try {
      statusBadge.textContent = 'Sending…';
      statusBadge.className = 'badge bg-info me-2';
      const res = await fetch('/api/rov/command', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ axes })
      });
      if (res.ok) {
        statusBadge.textContent = 'OK';
        statusBadge.className = 'badge bg-success me-2';
      } else {
        statusBadge.textContent = 'Error';
        statusBadge.className = 'badge bg-danger me-2';
      }
    } catch {
      statusBadge.textContent = 'Offline';
      statusBadge.className = 'badge bg-danger me-2';
    }
  }, SEND_INTERVAL);
})();
