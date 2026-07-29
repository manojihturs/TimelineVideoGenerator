from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile

from app.core import storage
from app.core.settings import ALLOWED_UPLOAD_EXTENSIONS, MAX_UPLOAD_BYTES, PREVIEW_ROW_COUNT
from app.models.dataset import DatasetPreview, DetectedColumns, UploadResponse
from app.services.column_detector import detect_columns
from app.services.dataset_service import load_dataframe

router = APIRouter(prefix="/api/uploads", tags=["uploads"])


def _load_dataset_or_404(dataset_id: str):
    path = storage.resolve_upload_path(dataset_id)
    if path is None:
        raise HTTPException(404, "Dataset not found")
    return load_dataframe(path)


@router.post("", response_model=UploadResponse)
async def upload_dataset(file: UploadFile):
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(400, f"Unsupported file type '{ext}'. Use CSV or XLSX.")

    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, "File too large.")

    dataset_id, path = storage.save_upload(file.filename, content)
    try:
        df = load_dataframe(path)
    except Exception as e:
        path.unlink(missing_ok=True)
        raise HTTPException(400, f"Could not read file: {e}")

    return UploadResponse(
        dataset_id=dataset_id,
        filename=file.filename,
        row_count=len(df),
        columns=[str(c) for c in df.columns],
    )


@router.post("/{dataset_id}/detect-columns", response_model=DetectedColumns)
def detect_dataset_columns(dataset_id: str):
    df = _load_dataset_or_404(dataset_id)
    return detect_columns(df)


@router.post("/{dataset_id}/preview", response_model=DatasetPreview)
def preview_dataset(dataset_id: str):
    df = _load_dataset_or_404(dataset_id)
    head = df.head(PREVIEW_ROW_COUNT).fillna("")
    return DatasetPreview(
        columns=[str(c) for c in df.columns],
        rows=head.to_dict(orient="records"),
    )
