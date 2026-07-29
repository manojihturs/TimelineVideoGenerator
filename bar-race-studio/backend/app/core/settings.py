"""Central, environment-overridable configuration — nothing dataset- or
deployment-specific is hardcoded elsewhere in the backend."""
import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
STORAGE_DIR = Path(os.environ.get("BAR_RACE_STORAGE_DIR", BACKEND_DIR / "storage"))
UPLOADS_DIR = STORAGE_DIR / "uploads"
RENDERS_DIR = STORAGE_DIR / "renders"
ASSETS_DIR = STORAGE_DIR / "assets"  # watermarks/logos, background music

MAX_UPLOAD_BYTES = int(os.environ.get("BAR_RACE_MAX_UPLOAD_MB", "50")) * 1024 * 1024
ALLOWED_UPLOAD_EXTENSIONS = {".csv", ".xlsx", ".xls"}

# how many rows to sample when running column-detection heuristics —
# full-file scans aren't needed to guess column roles, and staying small
# keeps detection fast even on large uploads
DETECTION_SAMPLE_ROWS = 200
PREVIEW_ROW_COUNT = 10

for d in (UPLOADS_DIR, RENDERS_DIR, ASSETS_DIR):
    d.mkdir(parents=True, exist_ok=True)
