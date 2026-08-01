// Top-level product tab switcher. Each button[data-tab="x"] shows/hides
// its matching #tab-x panel. Kept as a separate tiny script (not folded
// into app.js) since it has nothing to do with the Timeline tool's own
// state — it just decides which tool's panel is visible.
(function () {
  const tabs = document.querySelectorAll(".top-tab");
  const panels = document.querySelectorAll(".tab-panel");

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      const target = tab.dataset.tab;

      tabs.forEach((t) => t.classList.toggle("active", t === tab));
      panels.forEach((p) => p.classList.toggle("hidden", p.id !== `tab-${target}`));

      // Lazy-load the Bar Race Chart iframe on first visit only, so an
      // idle "Timeline" session never spins up its dev server traffic.
      if (target === "barrace") {
        const frame = document.getElementById("barrace-frame");
        if (frame && !frame.src && frame.dataset.src) {
          frame.src = frame.dataset.src;
        }
      }
    });
  });
})();
