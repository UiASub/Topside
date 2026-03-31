// graphs.js — Rolling IMU time-series with zoom, pan, axis locking,
//              crosshair tooltip, zero line, and CSV export
(function () {
  "use strict";

  const POLL_MS = 100;
  let windowSec = 30;
  let paused = false;

  // Chart.js dark-theme defaults
  Chart.defaults.color = "#adb5bd";
  Chart.defaults.borderColor = "rgba(255,255,255,0.08)";

  // ── Crosshair plugin (vertical + horizontal line at cursor) ──
  const crosshairPlugin = {
    id: "crosshair",
    afterDraw: function (chart) {
      var tooltip = chart.tooltip;
      if (!tooltip || !tooltip.caretX) return;
      var ctx = chart.ctx;
      var area = chart.chartArea;
      var x = tooltip.caretX;
      var y = tooltip.caretY;

      ctx.save();
      // Vertical line
      ctx.beginPath();
      ctx.setLineDash([4, 4]);
      ctx.lineWidth = 1;
      ctx.strokeStyle = "rgba(255,255,255,0.3)";
      ctx.moveTo(x, area.top);
      ctx.lineTo(x, area.bottom);
      ctx.stroke();
      // Horizontal line
      ctx.beginPath();
      ctx.moveTo(area.left, y);
      ctx.lineTo(area.right, y);
      ctx.stroke();
      ctx.restore();
    },
  };
  Chart.register(crosshairPlugin);

  // ── Zero-line plugin (dashed line at y=0) ──
  const zeroLinePlugin = {
    id: "zeroLine",
    beforeDraw: function (chart) {
      var yScale = chart.scales.y;
      if (yScale.min > 0 || yScale.max < 0) return; // 0 not in view
      var ctx = chart.ctx;
      var area = chart.chartArea;
      var yPixel = yScale.getPixelForValue(0);

      ctx.save();
      ctx.beginPath();
      ctx.setLineDash([6, 3]);
      ctx.lineWidth = 1;
      ctx.strokeStyle = "rgba(255,255,255,0.2)";
      ctx.moveTo(area.left, yPixel);
      ctx.lineTo(area.right, yPixel);
      ctx.stroke();
      ctx.restore();
    },
  };
  Chart.register(zeroLinePlugin);

  // Per-chart Y-axis locks: { min: number|null, max: number|null }
  const yLocks = {};

  // Store all raw samples for CSV export: { key: [{ x, y }, ...] }
  const allData = {};

  function makeChart(canvasId, label, unit, color, key) {
    yLocks[key] = { min: null, max: null };
    allData[key] = [];

    var ctx = document.getElementById(canvasId).getContext("2d");
    return new Chart(ctx, {
      type: "line",
      data: {
        datasets: [{
          label: label,
          data: allData[key],
          borderColor: color,
          borderWidth: 1.5,
          pointRadius: 0,
          tension: 0.2,
          fill: false,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        parsing: false,
        interaction: {
          mode: "nearest",
          axis: "x",
          intersect: false,
        },
        scales: {
          x: {
            type: "linear",
            title: { display: true, text: "Time (s)", font: { size: 10 } },
            ticks: { font: { size: 9 }, maxTicksLimit: 8 },
          },
          y: {
            title: { display: true, text: unit, font: { size: 10 } },
            ticks: { font: { size: 9 } },
          },
        },
        plugins: {
          legend: { display: false },
          tooltip: {
            enabled: true,
            callbacks: {
              title: function (items) {
                if (!items.length) return "";
                return "t = " + items[0].parsed.x.toFixed(1) + " s";
              },
              label: function (item) {
                return label + ": " + item.parsed.y.toFixed(2) + " " + unit;
              },
            },
            displayColors: false,
            backgroundColor: "rgba(0,0,0,0.8)",
            titleFont: { size: 11 },
            bodyFont: { size: 11 },
          },
          zoom: {
            pan: {
              enabled: true,
              mode: "xy",
              modifierKey: null,
            },
            zoom: {
              wheel: {
                enabled: true,
                modifierKey: null,
              },
              pinch: { enabled: true },
              mode: function (ctx) {
                // Shift+scroll = Y-axis zoom, default = X-axis zoom
                var evt = ctx.chart.canvas._lastWheelEvent;
                return (evt && evt.shiftKey) ? "y" : "x";
              },
            },
          },
        },
      },
    });
  }

  var charts = {};
  var chartDefs = {
    yaw:   { canvas: "chart-yaw",   label: "Yaw",        unit: "deg",   color: "#0dcaf0" },
    pitch: { canvas: "chart-pitch", label: "Pitch",       unit: "deg",   color: "#ffc107" },
    roll:  { canvas: "chart-roll",  label: "Roll",        unit: "deg",   color: "#198754" },
    yr:    { canvas: "chart-yr",    label: "Yaw Rate",    unit: "deg/s", color: "#0dcaf0" },
    pr:    { canvas: "chart-pr",    label: "Pitch Rate",  unit: "deg/s", color: "#ffc107" },
    rr:    { canvas: "chart-rr",    label: "Roll Rate",   unit: "deg/s", color: "#198754" },
  };

  for (var key in chartDefs) {
    var d = chartDefs[key];
    charts[key] = makeChart(d.canvas, d.label, d.unit, d.color, key);
  }

  var startTime = Date.now();

  function applyYLocks(key) {
    var yScale = charts[key].options.scales.y;
    var lock = yLocks[key];
    yScale.min = lock.min;
    yScale.max = lock.max;
  }

  function trimData(key) {
    var ds = allData[key];
    var now = (Date.now() - startTime) / 1000;
    var cutoff = now - windowSec;
    while (ds.length > 0 && ds[0].x < cutoff) {
      ds.shift();
    }
  }

  async function poll() {
    if (paused) return;
    try {
      var res = await fetch("/api/sensors");
      if (!res.ok) return;
      var d = await res.json();
      var t = parseFloat(((Date.now() - startTime) / 1000).toFixed(2));

      var values = {
        yaw: d.yaw || 0, pitch: d.pitch || 0, roll: d.roll || 0,
        yr: d.yr || 0, pr: d.pr || 0, rr: d.rr || 0,
      };

      for (var k in charts) {
        allData[k].push({ x: t, y: values[k] });
        trimData(k);
        applyYLocks(k);
        charts[k].update("none");
      }
    } catch (_) {
      // silent
    }
  }

  function clearAll() {
    for (var k in charts) {
      allData[k].length = 0;
      charts[k].resetZoom();
      charts[k].update();
    }
  }

  function resetAllZoom() {
    for (var k in charts) {
      charts[k].resetZoom();
    }
  }

  // ── CSV Export ──
  function exportCSV() {
    // Build a single CSV with all channels aligned by time
    // Collect all unique timestamps
    var timeSet = {};
    for (var k in allData) {
      allData[k].forEach(function (pt) { timeSet[pt.x] = true; });
    }
    var times = Object.keys(timeSet).map(Number).sort(function (a, b) { return a - b; });

    if (times.length === 0) {
      alert("No data to export.");
      return;
    }

    // Build lookup per channel: time -> value
    var lookup = {};
    var keys = ["yaw", "pitch", "roll", "yr", "pr", "rr"];
    keys.forEach(function (k) {
      lookup[k] = {};
      allData[k].forEach(function (pt) { lookup[k][pt.x] = pt.y; });
    });

    var header = "time_s,yaw_deg,pitch_deg,roll_deg,yaw_rate_dps,pitch_rate_dps,roll_rate_dps";
    var rows = [header];
    times.forEach(function (t) {
      var row = t.toFixed(2);
      keys.forEach(function (k) {
        var v = lookup[k][t];
        row += "," + (v !== undefined ? v.toFixed(3) : "");
      });
      rows.push(row);
    });

    var csv = rows.join("\n");
    var blob = new Blob([csv], { type: "text/csv" });
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url;
    var now = new Date();
    var ts = now.getFullYear() +
      String(now.getMonth() + 1).padStart(2, "0") +
      String(now.getDate()).padStart(2, "0") + "_" +
      String(now.getHours()).padStart(2, "0") +
      String(now.getMinutes()).padStart(2, "0") +
      String(now.getSeconds()).padStart(2, "0");
    a.download = "imu_data_" + ts + ".csv";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  // ── Pause button ──
  var btnPause = document.getElementById("btn-pause");

  function updatePauseButton() {
    btnPause.textContent = paused ? "Resume" : "Pause";
    btnPause.classList.toggle("btn-outline-warning", !paused);
    btnPause.classList.toggle("btn-warning", paused);
  }

  btnPause.addEventListener("click", function () {
    paused = !paused;
    updatePauseButton();
  });

  // ── Controls ──
  document.getElementById("time-window").addEventListener("change", function () {
    windowSec = parseInt(this.value, 10);
  });

  document.getElementById("btn-clear").addEventListener("click", clearAll);
  document.getElementById("btn-reset-zoom").addEventListener("click", resetAllZoom);
  document.getElementById("btn-export").addEventListener("click", exportCSV);

  // ── Y-axis lock inputs ──
  document.querySelectorAll("#graph-grid [data-key]").forEach(function (col) {
    var key = col.dataset.key;
    var minInput = col.querySelector(".y-min");
    var maxInput = col.querySelector(".y-max");
    var autoBtn = col.querySelector(".axis-auto");

    function applyInputs() {
      var minVal = minInput.value !== "" ? parseFloat(minInput.value) : null;
      var maxVal = maxInput.value !== "" ? parseFloat(maxInput.value) : null;
      yLocks[key].min = isNaN(minVal) ? null : minVal;
      yLocks[key].max = isNaN(maxVal) ? null : maxVal;
      applyYLocks(key);
      charts[key].update("none");
    }

    minInput.addEventListener("change", applyInputs);
    maxInput.addEventListener("change", applyInputs);

    autoBtn.addEventListener("click", function () {
      minInput.value = "";
      maxInput.value = "";
      yLocks[key].min = null;
      yLocks[key].max = null;
      applyYLocks(key);
      charts[key].resetZoom();
      charts[key].update("none");
    });
  });

  // ── Capture wheel event for shift-key detection in zoom mode ──
  for (var key in charts) {
    (function (k) {
      charts[k].canvas.addEventListener("wheel", function (e) {
        charts[k].canvas._lastWheelEvent = e;
      }, { passive: true });
    })(key);
  }

  // ── Double-click to reset zoom on individual chart ──
  for (var key in charts) {
    (function (k) {
      charts[k].canvas.addEventListener("dblclick", function () {
        charts[k].resetZoom();
      });
    })(key);
  }

  setInterval(poll, POLL_MS);
  poll();
})();
