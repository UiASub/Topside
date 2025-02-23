document.addEventListener("DOMContentLoaded", function () {
    const slider = document.getElementById("update-interval");
    const intervalDisplay = document.getElementById("interval-value");

    // Start with the default update interval of 500ms
    let batteryInterval = setInterval(updateBattery, 500);
    let depthInterval = setInterval(updateDepth, 500);
    let lightsInterval = setInterval(updateLights, 500);
    let sensorsInterval = setInterval(updateSensors, 500);
    let thrustersInterval = setInterval(updateThrusterStatus, 500)

    slider.addEventListener("input", function () {
        const newInterval = parseInt(slider.value);
        intervalDisplay.textContent = newInterval;

        // Clear previous intervals
        clearInterval(batteryInterval);
        clearInterval(depthInterval);
        clearInterval(lightsInterval);
        clearInterval(sensorsInterval);
        clearInterval(thrustersInterval);

        // Set new intervals with the updated time
        batteryInterval = setInterval(updateBattery, newInterval);
        depthInterval = setInterval(updateDepth, newInterval);
        lightsInterval = setInterval(updateLights, newInterval);
        sensorsInterval = setInterval(updateSensors, newInterval);
        thrustersInterval = setInterval(updateThrusterStatus, newInterval);
    });
});
