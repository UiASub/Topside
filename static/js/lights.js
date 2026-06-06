// lights.js – home dashboard light brightness slider.
// updateLights() is also driven on an interval by configuration.js.

let _lightPostTimer = null;

async function postLight(level) {
    try {
        await fetch("/api/lights", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ level }),
        });
    } catch (error) {
        console.error("Error setting lights:", error);
    }
}

// Throttle POSTs while the slider is being dragged.
function queueLightPost(level) {
    if (_lightPostTimer) return;
    _lightPostTimer = setTimeout(() => {
        _lightPostTimer = null;
    }, 100);
    postLight(level);
}

async function updateLights() {
    try {
        const response = await fetch("/api/lights");
        const data = await response.json();
        const pct = data.level ?? data.light ?? 0;
        const value = document.getElementById("light-value");
        const slider = document.getElementById("light-slider");
        if (value) value.textContent = pct;
        // Don't yank the slider out from under the user while they drag it.
        if (slider && document.activeElement !== slider) {
            slider.value = pct;
        }
    } catch (error) {
        console.error("Error fetching lights:", error);
    }
}

document.addEventListener("DOMContentLoaded", () => {
    const slider = document.getElementById("light-slider");
    const value = document.getElementById("light-value");
    if (!slider) return;

    slider.addEventListener("input", () => {
        const level = parseInt(slider.value, 10);
        if (value) value.textContent = level;
        queueLightPost(level);
    });
    // Guarantee the final position is sent even if the last input was throttled.
    slider.addEventListener("change", () => {
        postLight(parseInt(slider.value, 10));
    });

    updateLights();
});
