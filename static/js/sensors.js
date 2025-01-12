async function updateSensorData() {
    try {
        const response = await fetch('/api/sensor_data');
        const data = await response.json();
        const sensorElement = document.getElementById('sensor-data');
        sensorElement.innerHTML = `
            <p>Temperature: ${data.temperature}</p>
            <p>Pressure: ${data.pressure}</p>
            <p>Depth: ${data.depth}</p>
        `;
    } catch (error) {
        console.error('Error updating sensor data:', error);
    }
}

// Update the sensor data every second
setInterval(updateSensorData, 1000);
