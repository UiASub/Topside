async function updateBattery() {
  try {
    const response = await fetch("/api/battery");
    const data = await response.json();
    const batteryLevel = data.battery;

    // Update text
    const batteryStatus = document.getElementById("battery-status");
    batteryStatus.textContent = `Battery: ${batteryLevel}%`;

    // Update progress bar
    const batteryProgressEl = document.getElementById("battery-progress");
    batteryProgressEl.style.width = batteryLevel + "%";
    batteryProgressEl.setAttribute("aria-valuenow", batteryLevel);
    batteryProgressEl.textContent = `${batteryLevel}%`;

    // Dynamically change bar color based on battery level
    // Remove previous context classes first
    batteryProgressEl.classList.remove("bg-success", "bg-warning", "bg-danger");

    if (batteryLevel < 20) {
      batteryProgressEl.classList.add("bg-danger");
    } else if (batteryLevel < 50) {
      batteryProgressEl.classList.add("bg-warning");
    } else {
      batteryProgressEl.classList.add("bg-success");
    }
  } catch (error) {
    console.error("Error fetching battery:", error);
  }
}

// Update every 500ms
// setInterval(updateBattery, 500);
