"""Central, environment-overridable configuration — nothing dataset- or
deployment-specific is hardcoded elsewhere in the backend."""
import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
STORAGE_DIR = Path(os.environ.get("BAR_RACE_STORAGE_DIR", BACKEND_DIR / "storage"))
UPLOADS_DIR = STORAGE_DIR / "uploads"
RENDERS_DIR = Path(os.environ.get("BAR_RACE_RENDERS_DIR", r"C:\TimeLineVideo\BarRaceChart\RenderVideo"))
ASSETS_DIR = STORAGE_DIR / "assets"  # watermarks/logos, background music

# Drop zone for the auto-pipeline: the /format page's "Format & Auto
# Generate" button writes formatted CSVs into UNPROCESSED_DIR; folder_watcher
# picks them up, renders desktop+mobile videos, and moves the source file to
# PROCESSED_DIR (or FAILED_DIR if formatting/detection/render couldn't
# complete) so it's never re-picked-up. "Format" (format-only, no render)
# writes to FORMAT_ONLY_DIR instead — the watcher never looks there, so
# those files just sit ready for the user to review/move manually or drop
# into Unprocessed later via the "Auto-Generate" button.
UNPROCESSED_DIR = UPLOADS_DIR / "Unprocessed"
PROCESSED_DIR = UPLOADS_DIR / "Processed"
FAILED_DIR = UPLOADS_DIR / "Failed"
FORMAT_ONLY_DIR = UPLOADS_DIR / "Format"
# A file lives here for the whole render (moved out of Unprocessed the
# instant a scan claims it, before rendering even starts) so a second
# scan — or a fresh watcher after the process was restarted mid-render —
# can never pick up the same file again and render duplicate videos. On
# startup, anything still sitting here is a render that got interrupted
# last time the process died; it's moved back to Unprocessed exactly
# once so it gets retried, not left stuck or silently re-duplicated.
INPROGRESS_DIR = UPLOADS_DIR / "InProgress"

# Same end-video-append feature as this project's other app.py, reusing
# the same two files rather than requiring a second copy — bar-race-studio
# lives nested two directories under the project root they sit in.
PROJECT_ROOT = BACKEND_DIR.parent.parent
DESKTOP_END_VIDEO = Path(os.environ.get("BAR_RACE_DESKTOP_END_VIDEO", PROJECT_ROOT / "Desktop End video.mp4"))
MOBILE_END_VIDEO = Path(os.environ.get("BAR_RACE_MOBILE_END_VIDEO", PROJECT_ROOT / "Mobile End video.mp4"))

# Shown for INTRO_IMAGE_SECONDS at the very start of every render, before
# the chart animation begins — covers the canvas-capture engine's brief
# blank-white startup gap (page load + first paint) as a deliberate title
# card instead of an accidental flash. Desktop and mobile get their own
# image (different aspect ratios), same split as the end videos below.
WELCOME_IMAGE_DESKTOP = Path(os.environ.get("BAR_RACE_WELCOME_IMAGE_DESKTOP", PROJECT_ROOT / "Welcome pic desktop.png"))
WELCOME_IMAGE_MOBILE = Path(os.environ.get("BAR_RACE_WELCOME_IMAGE_MOBILE", PROJECT_ROOT / "Welcome pic mobile.png"))
INTRO_IMAGE_SECONDS = 2.5

# One track is picked at random per render when the user hasn't supplied
# their own music_asset_id — same "auto background music" behavior as
# this project's other app.py, reusing its already-cleared royalty-free
# folder rather than requiring a second copy.
MUSIC_DIR = Path(os.environ.get("BAR_RACE_MUSIC_DIR", PROJECT_ROOT / "music"))

# Persistent brand mark drawn bottom-left on every frame of the chart
# itself (distinct from RaceConfig.watermark_asset_id, which is a
# per-render opt-in the user configures per project — this one is fixed).
BRAND_LOGO = Path(os.environ.get("BAR_RACE_BRAND_LOGO", PROJECT_ROOT / "DataHunt Logo.png"))

MAX_UPLOAD_BYTES = int(os.environ.get("BAR_RACE_MAX_UPLOAD_MB", "50")) * 1024 * 1024
ALLOWED_UPLOAD_EXTENSIONS = {".csv", ".xlsx", ".xls"}

# how many rows to sample when running column-detection heuristics —
# full-file scans aren't needed to guess column roles, and staying small
# keeps detection fast even on large uploads
DETECTION_SAMPLE_ROWS = 200
PREVIEW_ROW_COUNT = 10

# folder_watcher's poll interval — the drop-folder pipeline is a
# convenience for unattended batch processing, not a low-latency path,
# so a few seconds of pickup delay is a fine trade for not needing a
# filesystem-events dependency (watchdog) on top of what the rest of the
# app already uses.
FOLDER_WATCH_INTERVAL_S = 5

for d in (UPLOADS_DIR, RENDERS_DIR, ASSETS_DIR, UNPROCESSED_DIR, PROCESSED_DIR, FAILED_DIR, FORMAT_ONLY_DIR, INPROGRESS_DIR):
    d.mkdir(parents=True, exist_ok=True)
