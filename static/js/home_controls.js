// home_controls.js – home dashboard control-mode buttons (frame toggle).

function setFrameButton(mode) {
    const btn = document.getElementById("frame-toggle");
    const status = document.getElementById("frame-status");
    if (!btn) return;
    const global = mode === "global";
    btn.textContent = "Frame: " + (global ? "GLOBAL" : "ROV");
    btn.classList.toggle("btn-info", global);
    btn.classList.toggle("btn-outline-info", !global);
    if (status) status.textContent = global ? "World / captured heading" : "Body-relative";
}

async function refreshFrame() {
    try {
        const res = await fetch("/api/controller/frame");
        const data = await res.json();
        if (data.ok) setFrameButton(data.frame);
    } catch (error) {
        /* ignore transient errors */
    }
}

async function toggleFrame() {
    try {
        const res = await fetch("/api/controller/frame", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ toggle: true }),
        });
        const data = await res.json();
        if (data.ok) setFrameButton(data.frame);
    } catch (error) {
        console.error("Error toggling frame:", error);
    }
}

document.addEventListener("DOMContentLoaded", () => {
    const frameBtn = document.getElementById("frame-toggle");
    if (frameBtn) frameBtn.addEventListener("click", toggleFrame);
    refreshFrame();
    // Reflect controller-button toggles made on the gamepad.
    setInterval(refreshFrame, 1000);
});
