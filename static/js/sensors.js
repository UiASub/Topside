// Calibration offset (set when user clicks calibrate)
let calibrationOffset = { roll: 0, pitch: 0, yaw: 0 };

let integratedYaw = 0;
let lastUpdateTime = null;

// Calculate roll and pitch from accelerometer (degrees)
function calcOrientation(accel) {
    const roll = Math.atan2(accel.y, accel.z) * (180 / Math.PI);
    const pitch = Math.atan2(-accel.x, Math.sqrt(accel.y * accel.y + accel.z * accel.z)) * (180 / Math.PI);
    return { roll, pitch };
}

function updateYaw(gyroZ) {
    const now = Date.now();
    if (lastUpdateTime !== null) {
        const dt = (now - lastUpdateTime) / 1000;
        integratedYaw += gyroZ * dt;
    }
    lastUpdateTime = now;
    return integratedYaw;
}

function applyCalibration(orientation) {
    return {
        roll: orientation.roll - calibrationOffset.roll,
        pitch: orientation.pitch - calibrationOffset.pitch,
        yaw: orientation.yaw - calibrationOffset.yaw
    };
}

function calibrate(accel) {
    const orientation = calcOrientation(accel);
    calibrationOffset = { roll: orientation.roll, pitch: orientation.pitch, yaw: orientation.yaw };
    integratedYaw = 0;
}

function getAngleStatus(angle, threshold = 15) {
    const absAngle = Math.abs(angle);
    if (absAngle < threshold / 2) return "status-ok";
    if (absAngle < threshold) return "status-warn";
    return "status-alert";
}

function formatAngle(val) {
    const num = parseFloat(val);
    return (num >= 0 ? "+" : "") + num.toFixed(0) + "°";
}

async function updateSensors() {
    try {
        const response = await fetch("/api/sensors");
        const data = await response.json();
        const sensorData = document.getElementById("sensor-data");

        const accel = data.acceleration;
        const gyro = data.gyroscope;

        // Calculate orientation with calibration applied
        const rawOrientation = calcOrientation(accel);
        const { roll, pitch } = applyCalibration(rawOrientation);
        const yaw = updateYaw(gyro.z);

        // Store latest accel for calibration button
        window.latestAccel = accel;

        sensorData.innerHTML = `
            <div class="sensor-orientation">
                <div class="orientation-item ${getAngleStatus(roll)}">
                    <span class="orientation-label">Roll</span>
                    <span class="orientation-value">${formatAngle(roll)}</span>
                </div>
                <div class="orientation-item ${getAngleStatus(pitch)}">
                    <span class="orientation-label">Pitch</span>
                    <span class="orientation-value">${formatAngle(pitch)}</span>
                </div>
                <div class="orientation-item status-ok">
                    <span class="orientation-label">Yaw</span>
                    <span class="orientation-value">${formatAngle(yaw)}</span>
                </div>
            </div>
            <div class="sensor-rates">
                <div class="rate-item">
                    <span class="rate-label">Roll Rate</span>
                    <span class="rate-value">${gyro.x.toFixed(1)}°/s</span>
                </div>
                <div class="rate-item">
                    <span class="rate-label">Pitch Rate</span>
                    <span class="rate-value">${gyro.y.toFixed(1)}°/s</span>
                </div>
                <div class="rate-item">
                    <span class="rate-label">Yaw Rate</span>
                    <span class="rate-value">${gyro.z.toFixed(1)}°/s</span>
                </div>
            </div>
        `;
    } catch (error) {
        console.error("Error fetching sensors:", error);
    }
}

setInterval(updateSensors, 100);
updateSensors();

document.getElementById("calibrate-btn").addEventListener("click", () => {
    if (window.latestAccel) {
        calibrate(window.latestAccel);
    }
});
