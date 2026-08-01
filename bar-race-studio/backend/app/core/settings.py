"""Central, environment-overridable configuration — nothing dataset- or
deployment-specific is hardcoded elsewhere in the backend."""
import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
STORAGE_DIR = Path(os.environ.get("BAR_RACE_STORAGE_DIR", BACKEND_DIR / "storage"))
UPLOADS_DIR = STORAGE_DIR / "uploads"
RENDERS_DIR = STORAGE_DIR / "renders"
ASSETS_DIR = STORAGE_DIR / "assets"  # watermarks/logos, background music

# Drop zone for the auto-pipeline: format_service writes formatted CSVs into
# UNPROCESSED_DIR; folder_watcher picks them up, renders desktop+mobile
# videos, and moves the source file to PROCESSED_DIR (or FAILED_DIR if
# formatting/detection/render couldn't complete) so it's never re-picked-up.
UNPROCESSED_DIR = UPLOADS_DIR / "Unprocessed"
PROCESSED_DIR = UPLOADS_DIR / "Processed"
FAILED_DIR = UPLOADS_DIR / "Failed"

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

for d in (UPLOADS_DIR, RENDERS_DIR, ASSETS_DIR, UNPROCESSED_DIR, PROCESSED_DIR, FAILED_DIR):
    d.mkdir(parents=True, exist_ok=True)
