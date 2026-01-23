/**
 * Resource Monitor - Dial Gauge Visualization
 * Displays CPU and Memory usage with animated SVG gauges
 */

// State tracking
let lastSequence = -1;
let packetsLost = 0;
let updateInterval = null;

/**
 * Calculate SVG arc path for a gauge
 * @param {number} percent - Value from 0 to 100
 * @returns {string} SVG path string
 */
function calculateArc(percent) {
    // Gauge spans 180 degrees (from left to right)
    const startAngle = Math.PI; // 180 degrees (left)
    const endAngle = 0; // 0 degrees (right)

    // Calculate the angle for the current percentage
    const angle = startAngle - (percent / 100) * Math.PI;

    const cx = 100; // Center X
    const cy = 100; // Center Y
    const r = 80;   // Radius

    // Start point (always left side)
    const startX = cx + r * Math.cos(startAngle);
    const startY = cy - r * Math.sin(startAngle);

    // End point (based on percentage)
    const endX = cx + r * Math.cos(angle);
    const endY = cy - r * Math.sin(angle);

    // Large arc flag (1 if > 180 degrees, but we're only going up to 180)
    const largeArc = percent > 50 ? 1 : 0;

    return `M ${startX} ${startY} A ${r} ${r} 0 ${largeArc} 1 ${endX} ${endY}`;
}

/**
 * Get color based on percentage value
 * @param {number} percent - Value from 0 to 100
 * @returns {string} CSS color value
 */
function getGaugeColor(percent) {
    if (percent < 50) {
        // Green to Yellow gradient
        const ratio = percent / 50;
        const r = Math.round(40 + ratio * 215);
        const g = Math.round(167 - ratio * 37);
        const b = Math.round(69 - ratio * 69);
        return `rgb(${r}, ${g}, ${b})`;
    } else {
        // Yellow to Red gradient
        const ratio = (percent - 50) / 50;
        const r = Math.round(255);
        const g = Math.round(130 - ratio * 130);
        const b = Math.round(0);
        return `rgb(${r}, ${g}, ${b})`;
    }
}

/**
 * Animate gauge to a new value
 * @param {string} arcId - ID of the arc path element
 * @param {string} valueId - ID of the value text element
 * @param {number} targetPercent - Target percentage value
 * @param {number} duration - Animation duration in ms
 */
function animateGauge(arcId, valueId, targetPercent, duration = 500) {
    const arcElement = document.getElementById(arcId);
    const valueElement = document.getElementById(valueId);

    if (!arcElement || !valueElement) return;

    const currentText = valueElement.textContent;
    const currentPercent = parseInt(currentText) || 0;
    const startTime = performance.now();

    function animate(currentTime) {
        const elapsed = currentTime - startTime;
        const progress = Math.min(elapsed / duration, 1);

        // Ease out cubic
        const easeProgress = 1 - Math.pow(1 - progress, 3);

        const currentValue = currentPercent + (targetPercent - currentPercent) * easeProgress;
        const roundedValue = Math.round(currentValue);

        // Update arc
        arcElement.setAttribute('d', calculateArc(currentValue));
        arcElement.style.stroke = getGaugeColor(currentValue);

        // Update text
        valueElement.textContent = `${roundedValue}%`;

        if (progress < 1) {
            requestAnimationFrame(animate);
        }
    }

    requestAnimationFrame(animate);
}

/**
 * Format uptime in human-readable format
 * @param {number} ms - Uptime in milliseconds
 * @returns {string} Formatted uptime string
 */
function formatUptime(ms) {
    const seconds = Math.floor(ms / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);
    const days = Math.floor(hours / 24);

    if (days > 0) {
        return `${days}d ${(hours % 24).toString().padStart(2, '0')}:${(minutes % 60).toString().padStart(2, '0')}:${(seconds % 60).toString().padStart(2, '0')}`;
    } else if (hours > 0) {
        return `${hours}:${(minutes % 60).toString().padStart(2, '0')}:${(seconds % 60).toString().padStart(2, '0')}`;
    } else {
        return `${minutes}:${(seconds % 60).toString().padStart(2, '0')}`;
    }
}

/**
 * Format large numbers with commas
 * @param {number} num - Number to format
 * @returns {string} Formatted number string
 */
function formatNumber(num) {
    return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

/**
 * Update the display with new telemetry data
 * @param {Object} data - Telemetry data object
 */
function updateDisplay(data) {
    // Update CPU gauge
    animateGauge('cpu-arc', 'cpu-value', data.cpu_percent, 300);

    // Update Memory gauge
    animateGauge('mem-arc', 'mem-value', data.heap_used_percent, 300);

    // Update memory details
    document.getElementById('mem-free').textContent = `Free: ${formatNumber(data.heap_free_kb)} KB`;
    document.getElementById('mem-total').textContent = `Total: ${formatNumber(data.heap_free_kb)} KB`;

    // Update stats
    document.getElementById('uptime').textContent = formatUptime(data.uptime_ms);
    document.getElementById('thread-count').textContent = data.thread_count;
    document.getElementById('udp-rx').textContent = formatNumber(data.udp_rx_count);
    document.getElementById('udp-errors').textContent = formatNumber(data.udp_rx_errors);

    // Update error badge color
    const errorBadge = document.getElementById('udp-errors');
    if (data.udp_rx_errors > 0) {
        errorBadge.classList.remove('stat-value');
        errorBadge.style.color = '#ff6b6b';
    }

    // Update sequence and packet loss
    document.getElementById('sequence').textContent = formatNumber(data.sequence);

    if (lastSequence >= 0 && data.sequence !== lastSequence + 1 && data.sequence !== 0) {
        const lost = data.sequence - lastSequence - 1;
        if (lost > 0) {
            packetsLost += lost;
        }
    }
    lastSequence = data.sequence;

    const lostBadge = document.getElementById('packets-lost');
    lostBadge.textContent = formatNumber(packetsLost);
    if (packetsLost > 0) {
        lostBadge.classList.remove('bg-secondary');
        lostBadge.classList.add('bg-warning');
    }

    // Update last update time
    const now = new Date();
    document.getElementById('last-update').textContent = now.toLocaleTimeString();

    // Update connection status
    document.getElementById('connection-status').textContent = 'Connected - Receiving telemetry';
    document.getElementById('connection-status').classList.remove('text-muted');
    document.getElementById('connection-status').classList.add('text-success');
}

/**
 * Fetch resource data from the API
 */
async function fetchResourceData() {
    try {
        const response = await fetch('/api/resources');
        if (!response.ok) {
            throw new Error(`HTTP error: ${response.status}`);
        }
        const data = await response.json();
        updateDisplay(data);
    } catch (error) {
        console.error('Error fetching resource data:', error);
        document.getElementById('connection-status').textContent = 'Connection error - retrying...';
        document.getElementById('connection-status').classList.remove('text-success');
        document.getElementById('connection-status').classList.add('text-danger');
    }
}

/**
 * Initialize the resource monitor
 */
function initResourceMonitor() {
    // Set initial gauge positions
    document.getElementById('cpu-arc').setAttribute('d', calculateArc(0));
    document.getElementById('mem-arc').setAttribute('d', calculateArc(0));

    // Start polling
    fetchResourceData();
    updateInterval = setInterval(fetchResourceData, 500);
}

// Start when DOM is ready
document.addEventListener('DOMContentLoaded', initResourceMonitor);

// Clean up on page unload
window.addEventListener('beforeunload', () => {
    if (updateInterval) {
        clearInterval(updateInterval);
    }
});
