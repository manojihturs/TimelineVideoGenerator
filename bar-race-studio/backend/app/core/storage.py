"""Upload file persistence — one responsibility: map a dataset_id to its
file on disk. Kept separate from dataset_service so swapping local disk
for S3/blob storage later only touches this module."""
import re
import uuid
from pathlib import Path

from app.core.settings import UPLOADS_DIR

_VALID_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def save_upload(filename: str, content: bytes) -> tuple[str, Path]:
    dataset_id = uuid.uuid4().hex[:12]
    ext = Path(filename).suffix.lower()
    dest = UPLOADS_DIR / f"{dataset_id}{ext}"
    dest.write_bytes(content)
    return dataset_id, dest


def resolve_upload_path(dataset_id: str) -> Path | None:
    if not _VALID_ID_RE.match(dataset_id):
        return None
    matches = list(UPLOADS_DIR.glob(f"{dataset_id}.*"))
    return matches[0] if matches else None
