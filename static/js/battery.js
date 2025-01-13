async function updateBattery() {
    try {
        const response = await fetch("/api/battery");
        const data = await response.json();
        const batteryStatus = document.getElementById("battery-status");
        batteryStatus.textContent = `Battery: ${data.battery}%`;
    } catch (error) {
        console.error("Error fetching battery:", error);
    }
}

setInterval(updateBattery, 500);
