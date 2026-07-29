"""Response models for the upload/detect/preview endpoints."""
from pydantic import BaseModel


class UploadResponse(BaseModel):
    dataset_id: str
    filename: str
    row_count: int
    columns: list[str]


class DetectedColumns(BaseModel):
    entity_column: str | None
    category_column: str | None
    image_column: str | None
    timeline_start_column: str | None
    timeline_end_column: str | None
    value_columns: list[str]
    timeline_format: str | None  # e.g. "YYYY-MM", "year", "month_name", "quarter", "week"


class DatasetPreview(BaseModel):
    columns: list[str]
    rows: list[dict]
