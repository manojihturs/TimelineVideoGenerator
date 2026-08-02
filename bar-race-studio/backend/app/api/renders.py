from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.core import storage
from app.models.config import RaceConfig
from app.models.render_job import FramesResponse
from app.services import job_manager
from app.services.dataframe_builder import build_long_dataframe, compute_frame_rankings, interpolate_frames
from app.services.dataset_service import load_dataframe

router = APIRouter(prefix="/api/renders", tags=["renders"])


@router.post("")
def create_render(config: RaceConfig):
    path = storage.resolve_upload_path(config.dataset_id)
    if path is None:
        raise HTTPException(404, "Dataset not found")

    # A bare, uncontextualized replay of a dataset (no title, no source
    # attribution) is exactly the kind of "reused content" YouTube's
    # monetization policy is strictest about. Requiring both fields here
    # doesn't guarantee monetization approval (that's YouTube's call on
    # the actual upload) but it does stop the app from producing videos
    # that fail the most basic bar for it.
    if not config.title.strip() or not config.data_source_label.strip():
        raise HTTPException(
            400,
            "Title and data source are required before exporting — YouTube's monetization "
            "policy for reused/aggregated data content expects both real context and a "
            "citation, not a bare chart replay.",
        )

    job_id = job_manager.start_render_job(config, str(path))
    return {"job_id": job_id}


@router.get("/{job_id}")
def get_render_status(job_id: str):
    job = job_manager.JOBS.get(job_id)
    if job is None:
        raise HTTPException(404, "Render job not found")
    return {"status": job["status"], "progress": job["progress"], "error": job["error"]}


@router.get("/{job_id}/download")
def download_render(job_id: str):
    job = job_manager.JOBS.get(job_id)
    if job is None:
        raise HTTPException(404, "Render job not found")
    if job["status"] != job_manager.RenderStatus.DONE or not job["output_path"]:
        raise HTTPException(409, f"Render is not finished (status: {job['status']})")
    return FileResponse(job["output_path"], filename=job.get("output_filename"))


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
    interpolated = interpolate_frames(
        long_df, steps_per_transition=steps,
        sort_direction=config.sort_direction, interpolation=config.interpolation,
    )
    ranked = compute_frame_rankings(interpolated, config.bar_count)

    frames = [
        {
            "frame_index": row.frame_index,
            "entity": row.entity,
            "category": row.category,
            "image_url": row.image_url,
            "value": row.value,
            "rank": row.rank,
        }
        for row in ranked.itertuples(index=False)
    ]
    return FramesResponse(frame_count=len(ranked["frame_index"].unique()) if not ranked.empty else 0, frames=frames)
