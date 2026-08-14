"""Upload endpoints for supporting media that isn't the dataset itself —
watermark/logo images and background music tracks. Stored the same way
as dataset uploads (storage.py's pattern), served back by asset_id so
they can be referenced from a RaceConfig without re-uploading."""
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.core.settings import ASSETS_DIR

router = APIRouter(prefix="/api/assets", tags=["assets"])

ALLOWED_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".svg", ".webp"}
ALLOWED_AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".ogg"}

_VALID_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _save_asset(file_bytes: bytes, filename: str, allowed_ext: set[str]) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in allowed_ext:
        raise HTTPException(400, f"Unsupported file type '{ext}'.")
    asset_id = uuid.uuid4().hex[:12]
    (ASSETS_DIR / f"{asset_id}{ext}").write_bytes(file_bytes)
    return asset_id


def resolve_asset_path(asset_id: str) -> Path | None:
    if not _VALID_ID_RE.match(asset_id):
        return None
    matches = list(ASSETS_DIR.glob(f"{asset_id}.*"))
    return matches[0] if matches else None


@router.post("/watermark")
async def upload_watermark(file: UploadFile):
    content = await file.read()
    asset_id = _save_asset(content, file.filename, ALLOWED_IMAGE_EXT)
    return {"asset_id": asset_id, "url": f"/api/assets/{asset_id}"}


@router.post("/music")
async def upload_music(file: UploadFile):
    content = await file.read()
    asset_id = _save_asset(content, file.filename, ALLOWED_AUDIO_EXT)
    return {"asset_id": asset_id, "url": f"/api/assets/{asset_id}"}


@router.get("/{asset_id}")
def get_asset(asset_id: str):
    path = resolve_asset_path(asset_id)
    if path is None:
        raise HTTPException(404, "Asset not found")
    return FileResponse(path)
