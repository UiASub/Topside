async function updateDepth() {
    try {
        const response = await fetch("/api/depth");
        const data = await response.json();
        const depthStatus = document.getElementById("depth-status");
        const depthTarget = document.getElementById("depth-target");
        const depthTemperature = document.getElementById("depth-temperature");
        const depthHealth = document.getElementById("depth-health");
        const depth = Number.parseFloat(data.dpt);
        const target = Number.parseFloat(data.dptSet);
        const temperature = Number.parseFloat(data.temperature_c);

        if (depthStatus) {
            depthStatus.textContent = Number.isFinite(depth) ? `${depth.toFixed(2)} m` : "--.-- m";
        }
        if (depthTarget) {
            depthTarget.textContent = Number.isFinite(target) ? `${target.toFixed(2)} m` : "-";
        }
        if (depthTemperature) {
            depthTemperature.textContent = Number.isFinite(temperature) ? `${temperature.toFixed(2)} °C` : "--.-- °C";
        }
        if (depthHealth) {
            const addr = Number(data.addr);
            const addrText = Number.isFinite(addr) && addr > 0 ? `0x${addr.toString(16).padStart(2, "0")}` : "--";
            if (data.valid) {
                depthHealth.textContent = `VALID age ${data.age_ms ?? "--"} ms addr ${addrText}`;
                depthHealth.className = "text-success mt-auto";
            } else {
                depthHealth.textContent = `INVALID err ${data.last_error ?? "--"} tries ${data.init_attempts ?? "--"} addr ${addrText}`;
                depthHealth.className = "text-warning mt-auto";
            }
        }
    } catch (error) {
        console.error("Error fetching depth:", error);
    }
}


// setInterval(updateDepth, 500);
