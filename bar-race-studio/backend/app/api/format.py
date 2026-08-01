"""POST /api/format — the "Format" button's endpoint. Takes any number of
raw CSV/XLSX files, reshapes each into the app's template via
csv_formatter, and writes the result into UNPROCESSED_DIR, where
folder_watcher picks it up and renders it automatically."""
import re
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, UploadFile
from pydantic import BaseModel

from app.core.settings import ALLOWED_UPLOAD_EXTENSIONS, UNPROCESSED_DIR
from app.services.csv_formatter import FormatError, format_dataframe
from app.services.dataset_service import load_dataframe

router = APIRouter(prefix="/api/format", tags=["format"])

_UNSAFE_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*]')


class FormatResult(BaseModel):
    filename: str
    success: bool
    saved_as: str | None = None
    error: str | None = None


def _safe_stem(filename: str) -> str:
    stem = Path(filename).stem.strip() or "dataset"
    return _UNSAFE_FILENAME_CHARS.sub("_", stem)


def _unique_destination(stem: str) -> Path:
    dest = UNPROCESSED_DIR / f"{stem}.csv"
    counter = 2
    while dest.exists():
        dest = UNPROCESSED_DIR / f"{stem}_{counter}.csv"
        counter += 1
    return dest


@router.post("", response_model=list[FormatResult])
async def format_files(files: list[UploadFile]) -> list[FormatResult]:
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
        tmp_path = UNPROCESSED_DIR / f"_incoming{ext}"
        try:
            tmp_path.write_bytes(content)
            df = load_dataframe(tmp_path)
            formatted = format_dataframe(df)

            dest = _unique_destination(_safe_stem(filename))
            formatted.to_csv(dest, index=False)
            results.append(FormatResult(filename=filename, success=True, saved_as=dest.name))
        except (FormatError, ValueError, pd.errors.ParserError) as e:
            results.append(FormatResult(filename=filename, success=False, error=str(e)))
        except Exception as e:
            results.append(FormatResult(filename=filename, success=False, error=f"Unexpected error: {e}"))
        finally:
            tmp_path.unlink(missing_ok=True)

    return results
