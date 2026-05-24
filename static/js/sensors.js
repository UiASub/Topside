function getAngleStatus(angle, threshold = 15) {
    const absAngle = Math.abs(angle);
    if (absAngle < threshold / 2) return "status-ok";
    if (absAngle < threshold) return "status-warn";
    return "status-alert";
}

function formatAngle(val) {
    const num = parseFloat(val);
    return (num >= 0 ? "+" : "") + num.toFixed(1) + "\u00B0";
}

function createOrientationItem(label, angle, statusClass) {
    const item = document.createElement("div");
    item.className = "orientation-item " + statusClass;
    const lbl = document.createElement("span");
    lbl.className = "orientation-label";
    lbl.textContent = label;
    const val = document.createElement("span");
    val.className = "orientation-value";
    val.textContent = formatAngle(angle);
    item.appendChild(lbl);
    item.appendChild(val);
    return item;
}

async function updateSensors() {
    try {
        const response = await fetch("/api/sensors");
        const data = await response.json();
        const sensorData = document.getElementById("sensor-data");

        const raw = {
            yaw: data.yaw || 0,
            pitch: data.pitch || 0,
            roll: data.roll || 0,
        };

        const { roll, pitch, yaw } = raw;

        sensorData.replaceChildren();
        const container = document.createElement("div");
        container.className = "sensor-orientation";
        container.appendChild(createOrientationItem("Roll", roll, getAngleStatus(roll)));
        container.appendChild(createOrientationItem("Pitch", pitch, getAngleStatus(pitch)));
        container.appendChild(createOrientationItem("Yaw", yaw, "status-ok"));
        sensorData.appendChild(container);
    } catch (error) {
        console.error("Error fetching sensors:", error);
    }
}

setInterval(updateSensors, 100);
updateSensors();
