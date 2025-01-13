async function updateSensors() {
    try {
        const response = await fetch("/api/sensors");
        const data = await response.json();
        const sensorData = document.getElementById("sensor-data");
        sensorData.innerHTML = `
            <p>Acceleration: x=${data.acceleration.x}, y=${data.acceleration.y}, z=${data.acceleration.z}</p>
            <p>Gyroscope: x=${data.gyroscope.x}, y=${data.gyroscope.y}, z=${data.gyroscope.z}</p>
            <p>Magnetometer: x=${data.magnetometer.x}, y=${data.magnetometer.y}, z=${data.magnetometer.z}</p>
        `;
    } catch (error) {
        console.error("Error fetching sensors:", error);
    }
}

setInterval(updateSensors, 500);
