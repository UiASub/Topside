/**
 * Fest Easter egg – type "fest" anywhere on the page to celebrate 🎉
 * Triggered by: typing the letters f-e-s-t in sequence.
 */
(function () {
  const TRIGGER = "fest";
  const PARTICLE_COUNT = 120;
  const DURATION_MS = 4000;
  const COLORS = [
    "#ff595e", "#ffca3a", "#6a4c93", "#1982c4",
    "#8ac926", "#ff6d00", "#00b4d8", "#e040fb",
  ];

  let buffer = "";

  document.addEventListener("keydown", (e) => {
    if (e.ctrlKey || e.altKey || e.metaKey) return;
    if (e.key.length !== 1) return;

    buffer = (buffer + e.key.toLowerCase()).slice(-TRIGGER.length);
    if (buffer === TRIGGER) {
      launchFest();
      buffer = "";
    }
  });

  function launchFest() {
    const container = document.createElement("div");
    container.setAttribute("aria-hidden", "true");
    Object.assign(container.style, {
      position: "fixed",
      top: "0",
      left: "0",
      width: "100%",
      height: "100%",
      pointerEvents: "none",
      overflow: "hidden",
      zIndex: "9999",
    });
    document.body.appendChild(container);

    for (let i = 0; i < PARTICLE_COUNT; i++) {
      spawnParticle(container);
    }

    setTimeout(() => container.remove(), DURATION_MS + 500);
  }

  function spawnParticle(container) {
    const el = document.createElement("div");
    const color = COLORS[Math.floor(Math.random() * COLORS.length)];
    const size = 8 + Math.random() * 8;
    const startX = Math.random() * 100;
    const delay = Math.random() * 1200;
    const spinDir = Math.random() < 0.5 ? 1 : -1;
    const shape = Math.random() < 0.5 ? "50%" : "0%";

    Object.assign(el.style, {
      position: "absolute",
      top: "-20px",
      left: startX + "%",
      width: size + "px",
      height: size + "px",
      backgroundColor: color,
      borderRadius: shape,
      opacity: "1",
      animation: `fest-fall ${DURATION_MS}ms ${delay}ms ease-in forwards`,
      transform: `rotate(${Math.random() * 360}deg)`,
    });

    el.animate(
      [
        {
          top: "-20px",
          transform: `rotate(0deg) translateX(0px)`,
          opacity: 1,
        },
        {
          top: "110%",
          transform: `rotate(${spinDir * (360 + Math.random() * 720)}deg) translateX(${(Math.random() - 0.5) * 80}px)`,
          opacity: 0.2,
        },
      ],
      {
        duration: DURATION_MS,
        delay: delay,
        easing: "ease-in",
        fill: "forwards",
      }
    );

    container.appendChild(el);
  }
})();
