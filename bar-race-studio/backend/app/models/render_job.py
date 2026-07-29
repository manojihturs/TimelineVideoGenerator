"""Response model for the frame-preview endpoint — a lightweight way to
inspect what the dataframe pipeline produces before any actual rendering
(Phase 4) exists."""
from pydantic import BaseModel


class FrameRow(BaseModel):
    frame_index: float
    entity: str
    category: str | None
    image_url: str | None
    value: float
    rank: int


class FramesResponse(BaseModel):
    frame_count: int
    frames: list[FrameRow]
