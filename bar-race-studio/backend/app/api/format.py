"""Backs the /format page's three buttons:
  - "Format" (mode=format_only): reshape and save to FORMAT_ONLY_DIR only —
    folder_watcher never looks there, so nothing gets auto-rendered.
  - "Format & Auto Generate" (mode=auto_generate, the default): reshape and
    save to UNPROCESSED_DIR, where folder_watcher picks it up and renders
    it on its own next poll.
  - "Auto-Generate": doesn't format anything — POST /api/format/run-now
    just wakes folder_watcher immediately instead of waiting up to
    FOLDER_WATCH_INTERVAL_S for whatever's already sitting in
    UNPROCESSED_DIR (dropped there directly, or by a previous "Format"
    step moved over manually)."""
import re
import threading
from pathlib import Path
from typing import Literal

import pandas as pd
from fastapi import APIRouter, Form, UploadFile
from pydantic import BaseModel

from app.core.settings import ALLOWED_UPLOAD_EXTENSIONS, FORMAT_ONLY_DIR, UNPROCESSED_DIR
from app.services.csv_formatter import FormatError, format_dataframe
from app.services.dataset_service import load_dataframe
from app.services.folder_watcher import scan_now

router = APIRouter(prefix="/api/format", tags=["format"])

_UNSAFE_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*]')

FormatMode = Literal["format_only", "auto_generate"]


class FormatResult(BaseModel):
    filename: str
    success: bool
    saved_as: str | None = None
    error: str | None = None


def _safe_stem(filename: str) -> str:
    stem = Path(filename).stem.strip() or "dataset"
    return _UNSAFE_FILENAME_CHARS.sub("_", stem)


def _unique_destination(dest_dir: Path, stem: str) -> Path:
    dest = dest_dir / f"{stem}.csv"
    counter = 2
    while dest.exists():
        dest = dest_dir / f"{stem}_{counter}.csv"
        counter += 1
    return dest


@router.post("", response_model=list[FormatResult])
async def format_files(files: list[UploadFile], mode: FormatMode = Form("auto_generate")) -> list[FormatResult]:
    dest_dir = FORMAT_ONLY_DIR if mode == "format_only" else UNPROCESSED_DIR
    results = []
    for file in files:
        filename = file.filename or "dataset"
        ext = Path(filename).suffix.lower()
        if ext not in ALLOWED_UPLOAD_EXTENSIONS:
            results.append(FormatResult(
                filename=filename, success=False,
                error=f"Unsupported file type '{ext}'. Use CSV or XLSX.",
            ))
            continue

        content = await file.read()
        tmp_path = dest_dir / f"_incoming{ext}"
        try:
            tmp_path.write_bytes(content)
            df = load_dataframe(tmp_path)
            formatted = format_dataframe(df)

            dest = _unique_destination(dest_dir, _safe_stem(filename))
            formatted.to_csv(dest, index=False)
            results.append(FormatResult(filename=filename, success=True, saved_as=dest.name))
        except (FormatError, ValueError, pd.errors.ParserError) as e:
            results.append(FormatResult(filename=filename, success=False, error=str(e)))
        except Exception as e:
            results.append(FormatResult(filename=filename, success=False, error=f"Unexpected error: {e}"))
        finally:
            tmp_path.unlink(missing_ok=True)

    return results


@router.post("/run-now")
def run_now() -> dict:
    """Triggers folder_watcher's scan immediately (in a background thread,
    so this returns right away rather than blocking on however long the
    renders take) instead of waiting for its next poll tick."""
    threading.Thread(target=scan_now, daemon=True).start()
    return {"status": "started"}
