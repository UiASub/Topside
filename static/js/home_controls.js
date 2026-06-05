// home_controls.js – home dashboard control-mode buttons (frame + dock).

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

function setDockButton(docked) {
    const btn = document.getElementById("docking-button");
    if (!btn) return;
    btn.textContent = docked ? "Docking: LOCKED" : "Docking";
    btn.classList.toggle("btn-warning", docked);
    btn.classList.toggle("btn-primary", !docked);
}

async function refreshControls() {
    try {
        const res = await fetch("/api/command/status", { cache: "no-store" });
        const data = await res.json();
        if (!data.ok) return;
        setFrameButton(data.frame);
        setDockButton(Boolean(data.docked));
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

async function toggleDock() {
    try {
        const res = await fetch("/api/dock/toggle", { method: "POST" });
        const data = await res.json();
        if (data.ok) setDockButton(Boolean(data.docked));
        else console.error("Dock toggle failed:", data.error);
    } catch (error) {
        console.error("Error toggling dock:", error);
    }
}

document.addEventListener("DOMContentLoaded", () => {
    const frameBtn = document.getElementById("frame-toggle");
    if (frameBtn) frameBtn.addEventListener("click", toggleFrame);
    const dockBtn = document.getElementById("docking-button");
    if (dockBtn) dockBtn.addEventListener("click", toggleDock);
    refreshControls();
    // Reflect toggles made from the gamepad too.
    setInterval(refreshControls, 1000);
});
