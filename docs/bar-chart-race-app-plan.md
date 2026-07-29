# Generic Bar Chart Race Studio — Architecture & Implementation Plan

A standalone web app (separate product from the actor/movie pipeline in this
repo) that turns any uploaded CSV/XLSX into an animated bar chart race video,
for any topic — no hardcoded dataset assumptions.

## 1. Project structure

```
bar-race-studio/
  frontend/                      # React + TypeScript + Vite + Tailwind
    src/
      api/                       # typed fetch wrappers around backend endpoints
        client.ts
        uploads.ts
        renders.ts
      components/
        upload/
          DropzoneUpload.tsx
          UploadProgress.tsx
        mapping/
          ColumnMappingScreen.tsx
          ColumnPicker.tsx
          TimelineRangePicker.tsx
        preview/
          DataPreviewTable.tsx
        settings/
          PropertyPanel.tsx        # left panel, grouped sections below
          panels/
            ChartTextPanel.tsx     # title/subtitle/source
            AnimationPanel.tsx     # fps, speed, transition, interpolation
            BarsPanel.tsx          # bar count, sort, orientation, color mode, width
            LabelsPanel.tsx        # show rank/value/category/axis/grid
            FormattingPanel.tsx    # currency/percent/number/date formatting
            ImagesPanel.tsx        # image column, fallback initials
            ExportPanel.tsx        # format, resolution, transparent bg
        preview-canvas/
          RacePreviewPlayer.tsx    # center: live/animated preview
          TimelineScrubber.tsx     # bottom: scrub through time steps
        layout/
          AppShell.tsx             # dark theme shell, 3-pane layout
      hooks/
        useFileUpload.ts
        useColumnDetection.ts
        useRaceConfig.ts           # central config state (Zustand/Context)
        useRenderJob.ts            # polls render job status
      models/
        RaceConfig.ts              # mirrors backend Pydantic config model
        DatasetSchema.ts
        RenderJob.ts
      utils/
        columnHeuristics.ts        # client-side "does this look numeric/date" helpers
        formatters.ts
      pages/
        UploadPage.tsx
        MappingPage.tsx
        StudioPage.tsx             # settings + preview + export, main editor
      App.tsx
      main.tsx
    tailwind.config.ts
    vite.config.ts
    package.json

  backend/                        # Python + FastAPI
    app/
      main.py                     # FastAPI app, router registration, CORS
      api/
        uploads.py                # POST /api/uploads
        columns.py                # POST /api/uploads/{id}/detect-columns
        preview.py                # POST /api/uploads/{id}/preview
        renders.py                # POST /api/renders, GET /api/renders/{id}
        assets.py                 # GET /api/renders/{id}/download
      services/
        dataset_service.py        # load CSV/XLSX -> pandas DataFrame
        column_detector.py        # heuristics: entity/category/image/timeline/numeric
        timeline_parser.py        # parse "1995-01" / "2010" / "Jan" / "Q1" / "Week 1" headers
        dataframe_builder.py      # wide -> long/interpolated frame ready for rendering
        image_resolver.py         # fetch/cache remote images, generate initials-avatar fallback
        race_renderer.py          # orchestrates bar_chart_race/matplotlib -> frames
        video_encoder.py          # ffmpeg/MoviePy: frames -> mp4/gif, resolution presets
        job_manager.py            # background job queue + status tracking
      models/
        config.py                 # RaceConfig Pydantic model (mirrors frontend model)
        dataset.py                # DetectedColumns, DatasetPreview
        render_job.py             # RenderJob, RenderStatus enum
      core/
        settings.py                # env config (storage paths, ffmpeg path, limits)
        storage.py                 # upload/temp/output file management
      workers/
        render_worker.py           # long-running render task (thread/process pool)
    tests/
      test_column_detector.py
      test_timeline_parser.py
      test_dataframe_builder.py
    pyproject.toml
    requirements.txt

  shared/
    race-config.schema.json        # single source of truth both FE/BE validate against

  docker-compose.yml                # frontend + backend + (optional) redis for job queue
```

Why this shape: the frontend never touches pandas/ffmpeg; the backend never
renders HTML. `race-config.schema.json` is the contract — both the Pydantic
model and the TypeScript model are generated from (or manually kept in sync
with) it, so "avoid hardcoded values" is enforced structurally, not by
convention.

## 2. Data model / configuration schema

This is the single object that fully describes one race — everything in the
"Bar Chart Race Settings" section of your spec becomes a field here, nothing
is a magic constant in render code.

```python
# backend/app/models/config.py
from enum import Enum
from pydantic import BaseModel

class SortDirection(str, Enum):
    ASCENDING = "ascending"
    DESCENDING = "descending"

class ColorMode(str, Enum):
    SINGLE = "single"
    CATEGORY = "category"
    RANDOM = "random"
    CUSTOM = "custom"

class ValueFormat(str, Enum):
    NUMBER = "number"
    CURRENCY = "currency"
    PERCENTAGE = "percentage"
    THOUSANDS = "thousands"
    MILLIONS = "millions"
    BILLIONS = "billions"

class ExportFormat(str, Enum):
    MP4 = "mp4"
    GIF = "gif"
    PNG_FRAMES = "png_frames"

class Resolution(str, Enum):
    HD_1080P = "1080p"
    QHD_1440P = "1440p"
    UHD_4K = "4k"
    VERTICAL_1080X1920 = "vertical_1080x1920"   # Shorts/Reels/TikTok

class Orientation(str, Enum):
    HORIZONTAL = "horizontal"   # classic racing bars, growing left-to-right
    VERTICAL = "vertical"       # racing columns, growing bottom-to-top

class ColumnMapping(BaseModel):
    entity_column: str
    category_column: str | None = None
    image_column: str | None = None
    timeline_start_column: str
    timeline_end_column: str
    # every column between start/end (inclusive) that parses as numeric
    # after header normalization is a timeline value column — detected,
    # not hardcoded, but the user can override the auto-picked set here
    value_columns: list[str]

class RaceConfig(BaseModel):
    dataset_id: str
    mapping: ColumnMapping

    title: str = ""
    subtitle: str = ""
    data_source_label: str = ""

    fps: int = 30
    animation_speed: float = 1.0          # multiplier on base per-step duration
    transition_duration_ms: int = 500
    interpolation: str = "easeInOut"       # linear | easeInOut | easeIn | easeOut

    bar_count: int = 10
    sort_direction: SortDirection = SortDirection.DESCENDING
    orientation: Orientation = Orientation.HORIZONTAL   # horizontal bars vs. vertical "racing columns"
    bar_color_mode: ColorMode = ColorMode.CATEGORY
    single_color: str | None = None
    custom_color_map: dict[str, str] | None = None   # entity/category -> hex
    bar_width_ratio: float = 0.8

    background_color: str = "#0B0F14"
    font_family: str = "Inter"
    label_size_px: int = 16

    show_images: bool = True
    show_category: bool = True
    show_rank: bool = True
    show_value: bool = True
    show_axis: bool = True
    show_grid: bool = False
    smooth_animation: bool = True

    value_format: ValueFormat = ValueFormat.NUMBER
    value_decimal_places: int = 0
    date_format: str = "YYYY-MM"

    export_format: ExportFormat = ExportFormat.MP4
    resolution: Resolution = Resolution.HD_1080P
    transparent_background: bool = False
```

This same shape (as a Zod schema, e.g. `RaceConfig.ts`) drives the React
property panel — each field maps to one control, so adding a new setting
later means adding one field, not touching render logic.

## 3. Column & timeline detection (the "intelligence" behind auto-mapping)

`column_detector.py` — heuristics, applied to a sampled slice of the
DataFrame (first ~200 rows) so detection is fast even on large files:

- **Entity column**: highest-cardinality non-numeric text column, or the
  first column if it's unique per row and mostly string.
- **Category column**: low-cardinality text column (few distinct values
  relative to row count) that isn't the entity column.
- **Image column**: any column whose values are mostly URL-shaped
  (`^https?://`) or end in `.png/.jpg/.jpeg/.svg/.webp`.
- **Timeline columns**: every remaining column whose *header* matches one
  of several patterns tried in order —
  `YYYY-MM`, `YYYY-MM-DD`, `YYYY` (bare year), `Q[1-4]` (optionally
  `YYYY-Q1`), `Week \d+`, month names/abbreviations (`Jan`…`Dec`), or a
  numeric sequence. First pattern that matches >50% of candidate headers
  wins; matched columns are sorted chronologically using that pattern's
  parser, not left-to-right file order (spreadsheets aren't always in
  order).
- **Numeric validation**: candidate timeline columns are coerced with
  `pd.to_numeric(errors="coerce")`; a column only qualifies if enough of
  its values (a threshold %) parse cleanly. Currency symbols, thousands
  separators, and percentage signs are stripped before coercion so
  `"$1,234"` / `"45%"` still count as numeric.

All of this produces a `DetectedColumns` suggestion object — the mapping
screen renders it as pre-filled dropdowns the user can override, never a
forced choice.

## 4. Backend flow (matches your 9 steps, made concrete)

```
POST /api/uploads
  -> save file to storage, sniff CSV/XLSX, read first sheet if XLSX
  -> returns { dataset_id, row_count, columns[] }

POST /api/uploads/{dataset_id}/detect-columns
  -> runs column_detector.py
  -> returns DetectedColumns (suggested mapping, editable by user)

POST /api/uploads/{dataset_id}/preview
  body: { mapping }  (user's confirmed/edited mapping)
  -> returns first 10 rows reshaped exactly as the render pipeline will see them
  -> lets the mapping screen show a live "does this look right" preview

POST /api/renders
  body: RaceConfig
  -> dataframe_builder.py: wide (one row per entity, one col per period)
     -> long/tidy frame: (entity, category, image_url, period, value)
     -> interpolates sub-frames between periods for smooth motion
     -> computes per-frame ranks (respecting bar_count + sort_direction)
  -> job_manager.py enqueues a RenderJob, returns { job_id, status: "queued" }

GET /api/renders/{job_id}
  -> { status: queued|rendering|encoding|done|failed, progress: 0-100, error? }

GET /api/renders/{job_id}/download
  -> streams the finished mp4/gif/zip-of-png-frames
```

Rendering itself (`race_renderer.py` + `video_encoder.py`):

1. `dataframe_builder` output (long-format, per-frame ranked values) is
   handed to a matplotlib/Plotly-based frame generator (or the
   `bar_chart_race` library as a starting point, though a hand-rolled
   matplotlib renderer gives more control over the exact settings list you
   specified — recommend starting with `bar_chart_race` for velocity, and
   forking to custom matplotlib once its config surface can't keep up with
   yours, e.g. per-category custom color maps, image avatars).
2. `image_resolver` fetches/caches every unique image URL once (not once
   per frame), draws a circular-cropped version, and falls back to a
   generated colored circle with the entity's initials when the URL is
   missing/broken/unset.
3. Frames render to a temp directory (or in-memory buffer for small races).
4. `video_encoder` calls ffmpeg (same pattern already used elsewhere in
   this repo — `-pix_fmt yuv420p`, resolution-specific scale/pad, optional
   alpha channel for transparent-background exports) to produce the final
   MP4/GIF; PNG-frames export just zips the frame directory.
5. `job_manager` updates progress throughout so the frontend's `TimelineScrubber`/
   progress bar reflects real state, not a fake spinner.

## 5. Frontend flow

```
UploadPage        -> DropzoneUpload -> POST /api/uploads -> navigate to MappingPage
MappingPage        -> GET detect-columns (auto-suggested)
                    -> ColumnMappingScreen (editable dropdowns)
                    -> DataPreviewTable (first 10 rows, live-updates on remap)
                    -> "Continue" -> navigate to StudioPage
StudioPage
  left:   PropertyPanel (all RaceConfig fields, grouped into the panels above)
  center: RacePreviewPlayer (renders a low-res/low-fps live preview client-side
          or via a cheap backend preview render — NOT the final export path)
  bottom: TimelineScrubber (scrub through detected periods)
  action: "Export" -> POST /api/renders -> useRenderJob polls status
          -> progress bar -> download link on completion
```

State: `useRaceConfig` holds the single `RaceConfig` object in a
Context/Zustand store; every settings panel reads/writes slices of it. This
keeps "avoid hardcoded values" true on the frontend too — no component
owns its own copy of a setting.

## 6. Database schema — is one needed?

Not for the core flow: uploads, mappings, and render jobs are transient
work objects, fine as files-on-disk + an in-memory/Redis job table (matches
this repo's existing `JOBS` dict pattern in `app.py`, just promoted to
Redis if you need multi-worker rendering). Add a real DB (SQLite to start,
same philosophy as the rest of this project — no infra overkill) only if
you want persistence across restarts for:

```sql
-- optional, only if "save my project and come back later" is a real requirement
CREATE TABLE datasets (
  id TEXT PRIMARY KEY,
  original_filename TEXT NOT NULL,
  uploaded_at TIMESTAMP NOT NULL,
  row_count INTEGER NOT NULL,
  columns_json TEXT NOT NULL          -- detected column list, cached
);

CREATE TABLE race_configs (
  id TEXT PRIMARY KEY,
  dataset_id TEXT NOT NULL REFERENCES datasets(id),
  name TEXT,
  config_json TEXT NOT NULL,          -- serialized RaceConfig
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL
);

CREATE TABLE render_jobs (
  id TEXT PRIMARY KEY,
  race_config_id TEXT NOT NULL REFERENCES race_configs(id),
  status TEXT NOT NULL,               -- queued|rendering|encoding|done|failed
  progress INTEGER NOT NULL DEFAULT 0,
  output_path TEXT,
  error TEXT,
  created_at TIMESTAMP NOT NULL,
  completed_at TIMESTAMP
);
```

## 7. Tech stack notes (matching what you specified)

- **Frontend**: React + TypeScript + Vite + Tailwind. Dark theme via
  Tailwind's `dark:` variants baked in as the only theme initially (spec
  lists "Multiple Themes" as a *future* feature, correctly deferred).
- **Backend**: FastAPI + Pandas + OpenPyXL (XLSX reading) + Matplotlib/Plotly
  (frame rendering) + `bar_chart_race` (fastest path to a working v1) +
  MoviePy/ffmpeg (encoding). Background rendering via FastAPI
  `BackgroundTasks` for v1; move to a real queue (Celery/RQ + Redis) once
  concurrent renders matter — same "start simple, don't over-engineer"
  posture as this repo's existing single-process Flask app.
- ffmpeg invocation should follow the same defensive patterns already
  proven out in this repo's `app.py` (`-movflags +faststart`, explicit
  `-pix_fmt yuv420p`, resolution-specific `scale`+`pad` filters) — those
  fixes came from real Windows Media Player compatibility failures earlier
  in this project and apply here too.

## 8. Step-by-step implementation plan

**Phase 0 — scaffolding (0.5–1 day)**
- Repo/workspace layout above, FastAPI hello-world + Vite hello-world,
  CORS wired, docker-compose for local dev.

**Phase 1 — upload & detection (2–3 days)**
- `/api/uploads`, `dataset_service.py` (CSV + XLSX first-sheet loading).
- `column_detector.py` + `timeline_parser.py` with unit tests covering all
  the header formats you listed (`YYYY-MM`, bare year, month names, `Qx`,
  `Week x`).
- `MappingPage` + `ColumnMappingScreen` + `DataPreviewTable`, wired to the
  detect/preview endpoints.

**Phase 2 — config & studio shell (2–3 days)**
- `RaceConfig` model (backend + frontend, kept in sync).
- `PropertyPanel` with all setting groups (start with sensible defaults
  rendering *something*, even before the real renderer exists — a stub
  preview).
- `AppShell` 3-pane dark-theme layout, drag-and-drop upload, progress bar
  component (reused for both upload and render progress).

**Phase 3 — dataframe pipeline (2–3 days)**
- `dataframe_builder.py`: wide -> long, interpolation between periods,
  per-frame ranking/`bar_count` truncation, respecting `sort_direction`.
- Unit tests with a synthetic dataset (small, deterministic) verifying
  frame-by-frame rank order matches hand-computed expectations.

**Phase 4 — rendering & encoding (3–5 days, the hard part)**
- `image_resolver.py`: fetch/cache/circular-crop/initials-fallback.
- `race_renderer.py`: frames via `bar_chart_race`/matplotlib, all
  `RaceConfig` fields actually wired to visual output (color mode, fonts,
  labels, grid, axis, transparent background).
- `video_encoder.py`: ffmpeg encode to MP4/GIF, resolution presets
  (1080p/1440p/4K/vertical), PNG-frame zip export.
- `job_manager.py` + progress reporting end-to-end.

**Phase 5 — export & polish (2 days)**
- `RacePreviewPlayer` + `TimelineScrubber` hooked to a cheap low-res
  preview render (not the full export pipeline).
- Full export flow: `StudioPage` -> `/api/renders` -> poll -> download.
- Error states (bad file, no numeric columns detected, render failure)
  surfaced clearly in the UI, not silent failures.

**Phase 6 — future features (explicitly out of v1 scope per your spec)**
- Watermark/logo upload, background music, voiceover, multiple themes,
  saved-project persistence (the optional DB schema above), social-preset
  shortcuts (Shorts/TikTok/Reels as named resolution+duration bundles on
  top of the existing `Resolution` enum).

## 9. Key design principles applied

- **Nothing dataset-specific in code.** Column roles are always resolved
  through the detection heuristics + user override, never assumed by name
  or position.
- **One config object, one source of truth**, mirrored FE/BE — every
  setting in your list is a field on it, not a scattered constant.
- **Detection ≠ decision.** Auto-mapping is a suggestion the mapping
  screen always lets the user correct before anything renders.
- **Render pipeline is stateless per job** — given the same `RaceConfig` +
  dataset, output is reproducible; no hidden global state (mirrors this
  repo's existing job-dict pattern, just generalized).
