from fastapi import APIRouter, HTTPException

from app.core import storage
from app.models.config import RaceConfig
from app.models.render_job import FramesResponse
from app.services.dataframe_builder import build_long_dataframe, compute_frame_rankings, interpolate_frames
from app.services.dataset_service import load_dataframe

router = APIRouter(prefix="/api/renders", tags=["renders"])


@router.post("/preview-frames", response_model=FramesResponse)
def preview_frames(config: RaceConfig):
    """Run the dataframe pipeline (wide -> long -> interpolated ->
    ranked) for the given RaceConfig and return the resulting frames as
    JSON — lets the pipeline be inspected/tested over real HTTP before
    Phase 4's actual frame rendering exists, and will back the real
    preview player once that lands."""
    path = storage.resolve_upload_path(config.dataset_id)
    if path is None:
        raise HTTPException(404, "Dataset not found")

    df = load_dataframe(path)
    long_df = build_long_dataframe(df, config.mapping)

    # 4 interpolated steps between each period keeps preview payloads
    # small while still demonstrating smooth interpolation; the real
    # renderer will derive this from fps/transition_duration_ms instead
    steps = 4 if config.smooth_animation else 0
    interpolated = interpolate_frames(long_df, steps_per_transition=steps)
    ranked = compute_frame_rankings(interpolated, config.bar_count, config.sort_direction)

    frames = [
        {
            "frame_index": row.frame_index,
            "entity": row.entity,
            "category": row.category,
            "image_url": row.image_url,
            "value": row.value,
            "rank": int(row.rank),
        }
        for row in ranked.itertuples(index=False)
    ]
    return FramesResponse(frame_count=len(ranked["frame_index"].unique()) if not ranked.empty else 0, frames=frames)
