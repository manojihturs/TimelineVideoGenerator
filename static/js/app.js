const FOLDER_STAGES = [
  { key: "Assets", icon: "▣", label: "Assets" },
  { key: "Thumbnail", icon: "◐", label: "Thumbnail" },
  { key: "Data", icon: "▤", label: "Data" },
  { key: "Export", icon: "▢", label: "Export" },
  { key: "Narration", icon: "♪", label: "Narration" },
];

const state = {
  currentTitle: null,
  device: "desktop",
  pollTimer: null,
};

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

// -------------------------------------------------------------------------
// view switching
// -------------------------------------------------------------------------

function showList() {
  $("#view-project").classList.add("hidden");
  $("#view-list").classList.remove("hidden");
  state.currentTitle = null;
  clearInterval(state.pollTimer);
  loadProjects();
}

function showProject(title) {
  state.currentTitle = title;
  $("#view-list").classList.add("hidden");
  $("#view-project").classList.remove("hidden");
  $("#render-panel").classList.add("hidden");
  loadProjectDetail(title);
}

// -------------------------------------------------------------------------
// project list
// -------------------------------------------------------------------------

async function loadProjects() {
  const res = await fetch("/api/projects");
  const projects = await res.json();
  const grid = $("#project-grid");
  grid.innerHTML = "";
  $("#empty-state").classList.toggle("hidden", projects.length > 0);

  for (const p of projects) {
    const card = document.createElement("div");
    card.className = "project-card";
    card.innerHTML = `
      <h3>${escapeHtml(p.title)}</h3>
      <div class="mini-strip">
        ${FOLDER_STAGES.map((s) => {
          let cls = "mini-frame";
          if (s.key === "Assets" && p.assets_ok) cls += " ready";
          else if (s.key === "Data" && p.csv_ok) cls += " ready";
          else if (p.folders_ok) cls += " on";
          return `<div class="${cls}"></div>`;
        }).join("")}
      </div>
      <div class="project-card-status ${p.ready ? "ready" : ""}">
        ${p.ready ? "ready to generate" : `${p.asset_count} asset(s) · csv ${p.csv_ok ? "ok" : "empty"}`}
      </div>
    `;
    card.addEventListener("click", () => showProject(p.title));
    grid.appendChild(card);
  }
}

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

$("#btn-new-project").addEventListener("click", () => {
  $("#new-project-panel").classList.remove("hidden");
  $("#input-title").focus();
});

$("#btn-cancel-project").addEventListener("click", () => {
  $("#new-project-panel").classList.add("hidden");
  $("#input-title").value = "";
  $("#create-error").classList.add("hidden");
});

$("#btn-create-project").addEventListener("click", async () => {
  const title = $("#input-title").value.trim();
  const errEl = $("#create-error");
  errEl.classList.add("hidden");

  if (!title) {
    errEl.textContent = "Title is required.";
    errEl.classList.remove("hidden");
    return;
  }

  const res = await fetch("/api/projects", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  const body = await res.json();

  if (!res.ok) {
    errEl.textContent = body.error || "Could not create project.";
    errEl.classList.remove("hidden");
    return;
  }

  $("#input-title").value = "";
  $("#new-project-panel").classList.add("hidden");
  showProject(body.title);
});

$("#input-title").addEventListener("keydown", (e) => {
  if (e.key === "Enter") $("#btn-create-project").click();
});

$("#btn-back").addEventListener("click", showList);

// -------------------------------------------------------------------------
// project workspace
// -------------------------------------------------------------------------

async function loadProjectDetail(title) {
  const res = await fetch(`/api/projects/${encodeURIComponent(title)}`);
  if (!res.ok) { showList(); return; }
  const p = await res.json();

  $("#project-title-h1").textContent = p.title;
  renderFilmstrip(p);
  renderChecklist(p);
  renderExports(p);
  renderThumbnailControls(p);
  renderThumbnailsList(p);
  updateGenerateAvailability(p);
}

function renderFilmstrip(p) {
  const strip = $("#filmstrip");
  strip.innerHTML = "";
  for (const stage of FOLDER_STAGES) {
    let cls = "strip-frame";
    if (stage.key === "Assets" && p.assets_ok) cls += " valid";
    else if (stage.key === "Data" && p.csv_ok) cls += " valid";
    else if (stage.key === "Thumbnail" && p.thumbnails && p.thumbnails.length > 0) cls += " valid";
    else if (stage.key === "Narration" && p.narration_ok) cls += " valid";
    else if (p.folders_ok) cls += " exists";

    const el = document.createElement("div");
    el.className = cls;
    el.innerHTML = `<span class="strip-icon">${stage.icon}</span><span class="strip-label">${stage.label}</span>`;
    strip.appendChild(el);
  }
}

function renderChecklist(p) {
  const list = $("#checklist");
  const items = [
    { ok: p.folders_ok, label: "Project folders created" },
    { ok: p.assets_ok, label: `Assets has numbered images (${p.asset_count} found)` },
    { ok: p.csv_ok, label: "Data/data.csv is not empty" },
    {
      ok: p.narration_ok,
      label: p.narration_ok
        ? `Narration audio found (${p.narration_count} file${p.narration_count === 1 ? "" : "s"}) — will be mixed in`
        : "Narration audio (optional) — none found, video will be silent",
      optional: true,
    },
  ];
  list.innerHTML = items
    .map((i) => {
      const cls = i.ok ? "ok" : i.optional ? "" : "bad";
      return `<li class="${cls}"><span class="dot"></span>${i.label}</li>`;
    })
    .join("");
}

function renderThumbnailControls(p) {
  const select = $("#select-thumb-source");
  select.innerHTML = p.asset_numbers
    .map((n) => `<option value="${n}">${n}.jpg</option>`)
    .join("");
  $("#btn-generate-thumb").disabled = p.asset_numbers.length === 0;
  $("#input-thumb-headline").placeholder = p.title;
}

function renderThumbnailsList(p) {
  // reuse the thumb-preview area to also link any already-generated thumbnails
  if (!p.thumbnails || p.thumbnails.length === 0) return;
  const wrap = $("#thumb-preview-wrap");
  const latest = p.thumbnails[p.thumbnails.length - 1];
  $("#thumb-preview").src = `/api/projects/${encodeURIComponent(p.title)}/thumbnail/${encodeURIComponent(latest)}?t=${Date.now()}`;
  wrap.classList.remove("hidden");
}

function renderExports(p) {
  const ul = $("#exports-list");
  ul.innerHTML = "";
  $("#no-exports").classList.toggle("hidden", p.exports.length > 0);
  for (const filename of p.exports) {
    const li = document.createElement("li");
    li.innerHTML = `<span>${escapeHtml(filename)}</span><a href="/api/projects/${encodeURIComponent(p.title)}/export/${encodeURIComponent(filename)}" download>Download</a>`;
    ul.appendChild(li);
  }
}

function updateGenerateAvailability(p) {
  const btn = $("#btn-generate");
  const reason = $("#generate-blocked-reason");
  btn.disabled = !p.ready;
  if (!p.ready) {
    const missing = [];
    if (!p.assets_ok) missing.push("add numbered images to Assets");
    if (!p.csv_ok) missing.push("fill in Data/data.csv");
    reason.textContent = `Before you can generate: ${missing.join(", ")}.`;
    reason.classList.remove("hidden");
  } else {
    reason.classList.add("hidden");
  }
}

// device toggle

$$(".device-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    $$(".device-btn").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    state.device = btn.dataset.device;
    $("#desktop-controls").classList.toggle("hidden", state.device !== "desktop");
    $("#mobile-controls").classList.toggle("hidden", state.device !== "mobile");
  });
});

// generate

$("#btn-generate").addEventListener("click", async () => {
  const title = state.currentTitle;
  const payload = { device: state.device };

  if (state.device === "desktop") {
    payload.minutes = parseInt($("#input-minutes").value || "0", 10);
    payload.seconds = parseInt($("#input-seconds").value || "0", 10);
    payload.resolution = $("#select-resolution").value;
  } else {
    payload.seconds = parseInt($("#input-mobile-seconds").value || "0", 10);
  }

  const res = await fetch(`/api/projects/${encodeURIComponent(title)}/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const body = await res.json();

  if (!res.ok) {
    $("#generate-blocked-reason").textContent = body.error || "Could not start render.";
    $("#generate-blocked-reason").classList.remove("hidden");
    return;
  }

  $("#render-panel").classList.remove("hidden");
  $("#download-link").classList.add("hidden");
  $("#progress-fill").style.width = "0%";
  $("#render-message").textContent = "Starting…";
  pollJob(body.job_id, title);
});

$("#btn-generate-thumb").addEventListener("click", async () => {
  const title = state.currentTitle;
  const errEl = $("#thumb-error");
  errEl.classList.add("hidden");

  const payload = {
    device: $("#select-thumb-device").value,
    source: $("#select-thumb-source").value,
    headline: $("#input-thumb-headline").value.trim() || title,
  };

  const btn = $("#btn-generate-thumb");
  btn.disabled = true;
  btn.textContent = "Generating…";

  try {
    const res = await fetch(`/api/projects/${encodeURIComponent(title)}/thumbnail`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const body = await res.json();

    if (!res.ok) {
      errEl.textContent = body.error || "Could not generate thumbnail.";
      errEl.classList.remove("hidden");
      return;
    }

    const wrap = $("#thumb-preview-wrap");
    $("#thumb-preview").src = `/api/projects/${encodeURIComponent(title)}/thumbnail/${encodeURIComponent(body.thumbnail)}?t=${Date.now()}`;
    wrap.classList.remove("hidden");
    loadProjectDetail(title); // refresh filmstrip/checklist status
  } finally {
    btn.disabled = false;
    btn.textContent = "Generate thumbnail";
  }
});

function pollJob(jobId, title) {
  clearInterval(state.pollTimer);
  state.pollTimer = setInterval(async () => {
    const res = await fetch(`/api/jobs/${jobId}`);
    const job = await res.json();

    $("#progress-fill").style.width = `${job.progress}%`;
    $("#render-message").textContent = job.message;

    if (job.status === "done") {
      clearInterval(state.pollTimer);
      const link = $("#download-link");
      link.href = `/api/projects/${encodeURIComponent(title)}/export/${encodeURIComponent(job.output_path)}`;
      link.classList.remove("hidden");
      loadProjectDetail(title);
    } else if (job.status === "error") {
      clearInterval(state.pollTimer);
      $("#render-message").textContent = "Error: " + job.message;
    }
  }, 1200);
}

// -------------------------------------------------------------------------
// boot
// -------------------------------------------------------------------------

showList();
