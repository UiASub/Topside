async function updateThrusterStatus() {
    try {
        const response = await fetch("/api/thrusters");
        const data = await response.json();

        const thrusterTable = document.getElementById("thruster-status-table");
        thrusterTable.innerHTML = `
            <tr>
                <th>Thruster</th>
                <th>Power (W)</th>
                <th>Temperature (°C)</th>
            </tr>
        `;

        for (const [name, stats] of Object.entries(data)) {
            thrusterTable.innerHTML += `
                <tr>
                    <td>${name}</td>
                    <td>${stats.power}</td>
                    <td>${stats.temp}</td>
                </tr>
            `;
        }
    } catch (error) {
        console.error("Error fetching thruster data:", error);
    }
}

// Update intervall
// setInterval(updateThrusterStatus, 500);
