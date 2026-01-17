/**
 * Resource Monitor Bar - CPU & RAM display
 */

function getBarColor(percent) {
    if (percent < 50) {
        return '#28a745'; // green
    } else if (percent < 80) {
        return '#ffc107'; // yellow
    } else {
        return '#dc3545'; // red
    }
}

function formatUptime(ms) {
    const seconds = Math.floor(ms / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);
    const days = Math.floor(hours / 24);

    if (days > 0) {
        return `${days}d ${(hours % 24)}h`;
    } else if (hours > 0) {
        return `${hours}h ${(minutes % 60)}m`;
    } else {
        return `${minutes}m ${(seconds % 60)}s`;
    }
}

function updateBar(barId, valueId, percent) {
    const bar = document.getElementById(barId);
    const value = document.getElementById(valueId);
    if (bar && value) {
        bar.style.width = `${percent}%`;
        bar.style.backgroundColor = getBarColor(percent);
        value.textContent = `${percent}%`;
    }
}

async function updateResources() {
    try {
        const response = await fetch('/api/resources');
        const data = await response.json();

        updateBar('cpu-bar', 'cpu-value', data.cpu_percent || 0);
        updateBar('ram-bar', 'ram-value', data.heap_used_percent || 0);

        const uptimeEl = document.getElementById('uptime-value');
        if (uptimeEl) {
            uptimeEl.textContent = formatUptime(data.uptime_ms || 0);
        }

        const threadEl = document.getElementById('thread-value');
        if (threadEl) {
            threadEl.textContent = data.thread_count || 0;
        }
    } catch (error) {
        console.error('Error fetching resource data:', error);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    updateResources();
    setInterval(updateResources, 1000);
});
