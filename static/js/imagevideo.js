// Image to Video tab — upload images, render one video per image with
// mixed-in background music. Kept as its own tiny script (like tabs.js)
// rather than folded into app.js, since it has nothing to do with the
// Timeline tool's own state.
(function () {
  const imagesInput = document.getElementById("iv-images");
  const destInput = document.getElementById("iv-dest");
  const generateBtn = document.getElementById("iv-generate");
  const errorEl = document.getElementById("iv-error");
  const progressWrap = document.getElementById("iv-progress-wrap");
  const progressFill = document.getElementById("iv-progress-fill");
  const progressPercent = document.getElementById("iv-progress-percent");
  const timerEl = document.getElementById("iv-timer");
  const messageEl = document.getElementById("iv-message");
  const resultsEl = document.getElementById("iv-results");

  if (!generateBtn) return; // tab not present on this page

  let pollTimer = null;
  let tickTimer = null;

  function formatElapsed(ms) {
    const total = Math.floor(ms / 1000);
    const m = Math.floor(total / 60);
    const s = total % 60;
    return `${m}:${String(s).padStart(2, "0")}`;
  }

  function showError(message) {
    errorEl.textContent = message;
    errorEl.classList.remove("hidden");
  }

  function clearError() {
    errorEl.textContent = "";
    errorEl.classList.add("hidden");
  }

  function renderResults(results) {
    resultsEl.innerHTML = "";
    (results || []).forEach((r) => {
      const li = document.createElement("li");
      li.textContent = r.ok ? `✓ ${r.file} → ${r.output}` : `✗ ${r.file}: ${r.error}`;
      resultsEl.appendChild(li);
    });
  }

  function stopPolling() {
    if (pollTimer) clearInterval(pollTimer);
    if (tickTimer) clearInterval(tickTimer);
    pollTimer = null;
    tickTimer = null;
  }

  function pollJob(jobId) {
    stopPolling();
    const startTime = Date.now();
    tickTimer = setInterval(() => {
      timerEl.textContent = `Elapsed ${formatElapsed(Date.now() - startTime)}`;
    }, 1000);

    pollTimer = setInterval(async () => {
      let job;
      try {
        const res = await fetch(`/api/jobs/${jobId}`);
        if (!res.ok) throw new Error(`status ${res.status}`);
        job = await res.json();
      } catch (e) {
        stopPolling();
        generateBtn.disabled = false;
        showError("Lost track of the render job — check the server log.");
        return;
      }

      progressFill.style.width = `${job.progress}%`;
      progressPercent.textContent = `${job.progress}%`;
      messageEl.textContent = job.message;

      if (job.status === "done" || job.status === "error") {
        stopPolling();
        generateBtn.disabled = false;
        if (job.status === "error") showError(job.message || "Render failed.");
        renderResults(job.results);
      }
    }, 1000);
  }

  generateBtn.addEventListener("click", async () => {
    clearError();
    resultsEl.innerHTML = "";

    const files = imagesInput.files;
    if (!files || files.length === 0) {
      showError("Select at least one image.");
      return;
    }
    const destDir = destInput.value.trim();
    if (!destDir) {
      showError("Enter a destination folder.");
      return;
    }
    const durationInput = document.querySelector('input[name="iv-duration"]:checked');
    const duration = durationInput ? durationInput.value : "30";

    const formData = new FormData();
    for (const file of files) formData.append("images", file);
    formData.append("dest_dir", destDir);
    formData.append("duration", duration);

    generateBtn.disabled = true;
    progressWrap.classList.remove("hidden");
    progressFill.style.width = "0%";
    progressPercent.textContent = "0%";
    timerEl.textContent = "Elapsed 0:00";
    messageEl.textContent = "Starting…";

    try {
      const res = await fetch("/api/image-to-video/render", { method: "POST", body: formData });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(body.error || `Request failed: ${res.status}`);
      }
      pollJob(body.job_id);
    } catch (e) {
      generateBtn.disabled = false;
      progressWrap.classList.add("hidden");
      showError(e instanceof Error ? e.message : "Failed to start render.");
    }
  });
})();
