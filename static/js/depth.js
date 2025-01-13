async function updateDepth() {
    try {
        const response = await fetch("/api/depth");
        const data = await response.json();
        const depthStatus = document.getElementById("depth-status");
        depthStatus.textContent = `Depth: ${data.dpt}m / Target: ${data.dptSet}m`;
    } catch (error) {
        console.error("Error fetching depth:", error);
    }
}


setInterval(updateDepth, 500);
