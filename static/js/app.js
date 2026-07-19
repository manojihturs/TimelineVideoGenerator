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
  categories: [],
  selectedCategory: null,
  fetchPollTimer: null,
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
  await ensureCategoriesLoaded();
  applyProjectCategory(p.category);
}

// -------------------------------------------------------------------------
// content / categories
// -------------------------------------------------------------------------

async function ensureCategoriesLoaded() {
  if (state.categories.length > 0) return;
  const res = await fetch("/api/categories");
  state.categories = await res.json();
  const select = $("#select-category");
  select.innerHTML =
    `<option value="">— none —</option>` +
    state.categories.map((c) => `<option value="${escapeHtml(c.name)}">${escapeHtml(c.name)}</option>`).join("");
}

function categoryByName(name) {
  return state.categories.find((c) => c.name === name) || null;
}

function applyProjectCategory(categoryName) {
  $("#select-category").value = categoryName || "";
  state.selectedCategory = categoryByName(categoryName);
  renderItemsTableHead();
  resetItemsTableBody();
}

$("#select-category").addEventListener("change", async () => {
  const title = state.currentTitle;
  const categoryName = $("#select-category").value;

  await fetch(`/api/projects/${encodeURIComponent(title)}/category`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ category: categoryName }),
  });

  state.selectedCategory = categoryByName(categoryName);
  renderItemsTableHead();
  resetItemsTableBody();
});

function renderItemsTableHead() {
  const head = $("#items-table-head");
  const columns = state.selectedCategory ? state.selectedCategory.columns : [];
  head.innerHTML =
    `<th>#</th><th>Search query</th>` +
    columns.map((c) => `<th>${escapeHtml(c)}</th>`).join("") +
    `<th></th>`;

  const wrap = $("#items-table-wrap");
  const fetchBtn = $("#btn-fetch-items");
  const hasCategory = !!state.selectedCategory;
  wrap.classList.toggle("hidden", !hasCategory);
  fetchBtn.classList.toggle("hidden", !hasCategory);

  const hasAutoSource = !!(state.selectedCategory && state.selectedCategory.auto_source);
  $("#auto-fetch-section").classList.toggle("hidden", !hasAutoSource);
}

$("#btn-auto-fetch").addEventListener("click", async () => {
  const title = state.currentTitle;
  const errEl = $("#auto-fetch-error");
  errEl.classList.add("hidden");

  const topic = $("#input-topic").value.trim();
  if (!topic) {
    errEl.textContent = "Enter a topic (e.g. an actor's name).";
    errEl.classList.remove("hidden");
    return;
  }

  const btn = $("#btn-auto-fetch");
  btn.disabled = true;
  btn.textContent = "Fetching…";

  const res = await fetch(`/api/projects/${encodeURIComponent(title)}/auto-fetch`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ category: state.selectedCategory ? state.selectedCategory.name : null, topic }),
  });
  const body = await res.json();

  if (!res.ok) {
    errEl.textContent = body.error || "Could not start auto-fetch.";
    errEl.classList.remove("hidden");
    btn.disabled = false;
    btn.textContent = "Auto-fetch filmography";
    return;
  }

  $("#fetch-panel").classList.remove("hidden");
  $("#fetch-progress-fill").style.width = "0%";
  $("#fetch-message").textContent = "Starting…";
  pollFetchJob(body.job_id, title, btn, "Auto-fetch filmography");
});

function resetItemsTableBody() {
  $("#items-table-body").innerHTML = "";
  if (state.selectedCategory) addItemRow();
}

function addItemRow() {
  const columns = state.selectedCategory ? state.selectedCategory.columns : [];
  const body = $("#items-table-body");
  const tr = document.createElement("tr");
  tr.innerHTML =
    `<td class="row-num"></td>` +
    `<td><input class="field-input item-query" type="text" placeholder="e.g. Top Gun 1986" /></td>` +
    columns.map((c) => `<td><input class="field-input item-col" type="text" placeholder="${escapeHtml(c)}" /></td>`).join("") +
    `<td><button type="button" class="btn-remove-row" title="Remove">×</button></td>`;
  tr.querySelector(".btn-remove-row").addEventListener("click", () => {
    tr.remove();
    renumberItemRows();
  });
  body.appendChild(tr);
  renumberItemRows();
}

function renumberItemRows() {
  $$("#items-table-body tr").forEach((tr, i) => {
    tr.querySelector(".row-num").textContent = `${i + 1}.`;
  });
}

$("#btn-add-item-row").addEventListener("click", addItemRow);

$("#btn-fetch-items").addEventListener("click", async () => {
  const title = state.currentTitle;
  const errEl = $("#items-error");
  errEl.classList.add("hidden");

  const rows = Array.from($$("#items-table-body tr"));
  const items = rows.map((tr) => {
    const query = tr.querySelector(".item-query").value.trim();
    const row = Array.from(tr.querySelectorAll(".item-col")).map((i) => i.value.trim());
    return { query, row };
  });

  if (items.length === 0 || items.some((it) => !it.query || it.row.some((v) => !v))) {
    errEl.textContent = "Every row needs a search query and a value in every column.";
    errEl.classList.remove("hidden");
    return;
  }

  const btn = $("#btn-fetch-items");
  btn.disabled = true;
  btn.textContent = "Fetching…";

  const res = await fetch(`/api/projects/${encodeURIComponent(title)}/items`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ category: state.selectedCategory ? state.selectedCategory.name : null, items }),
  });
  const body = await res.json();

  if (!res.ok) {
    errEl.textContent = body.error || "Could not start fetch.";
    errEl.classList.remove("hidden");
    btn.disabled = false;
    btn.textContent = "Fetch content";
    return;
  }

  $("#fetch-panel").classList.remove("hidden");
  $("#fetch-progress-fill").style.width = "0%";
  $("#fetch-message").textContent = "Starting…";
  pollFetchJob(body.job_id, title, btn);
});

function pollFetchJob(jobId, title, btn, resetLabel) {
  resetLabel = resetLabel || "Fetch content";
  clearInterval(state.fetchPollTimer);
  state.fetchPollTimer = setInterval(async () => {
    const res = await fetch(`/api/jobs/${jobId}`);
    const job = await res.json();

    $("#fetch-progress-fill").style.width = `${job.progress}%`;
    $("#fetch-message").textContent = job.message;

    if (job.status === "done") {
      clearInterval(state.fetchPollTimer);
      btn.disabled = false;
      btn.textContent = resetLabel;
      loadProjectDetail(title);
    } else if (job.status === "error") {
      clearInterval(state.fetchPollTimer);
      btn.disabled = false;
      btn.textContent = resetLabel;
      $("#fetch-message").textContent = "Error: " + job.message;
    }
  }, 1200);
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
    const maxItems = $("#input-mobile-max-items").value.trim();
    if (maxItems) payload.max_items = parseInt(maxItems, 10);
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

$("#btn-add-music").addEventListener("click", async () => {
  const title = state.currentTitle;
  const errEl = $("#music-error");
  const resultEl = $("#music-result");
  errEl.classList.add("hidden");
  resultEl.classList.add("hidden");

  const btn = $("#btn-add-music");
  btn.disabled = true;
  btn.textContent = "Fetching…";

  try {
    const res = await fetch(`/api/projects/${encodeURIComponent(title)}/music`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tags: $("#input-music-tags").value.trim() }),
    });
    const body = await res.json();

    if (!res.ok) {
      errEl.textContent = body.error || "Could not fetch music.";
      errEl.classList.remove("hidden");
      return;
    }

    resultEl.textContent = `Added: ${body.attribution}`;
    resultEl.classList.remove("hidden");
    loadProjectDetail(title); // refresh narration status in checklist
  } finally {
    btn.disabled = false;
    btn.textContent = "Add background music";
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
