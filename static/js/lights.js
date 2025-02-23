async function updateLights() {
    try {
        const response = await fetch("/api/lights");
        const data = await response.json();
        const lightData = document.getElementById("light-data");
        lightData.innerHTML = Object.entries(data)
            .map(([name, brightness]) => `<p>${name}: ${brightness}%</p>`)
            .join("");
    } catch (error) {
        console.error("Error fetching lights:", error);
    }
}

// setInterval(updateLights, 500);
