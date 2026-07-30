"""In-memory background job tracking — same simple pattern as this
repo's other Flask app (a plain dict + daemon thread), appropriate for a
single-process dev server. Swap for Redis/RQ only once concurrent
renders across multiple workers actually matters."""
import os
import shutil
import threading
import uuid
from enum import Enum

from app.api.assets import resolve_asset_path
from app.core.settings import RENDERS_DIR
from app.models.config import ExportFormat, RaceConfig
from app.services.dataframe_builder import build_long_dataframe, compute_frame_rankings, interpolate_frames
from app.services.dataset_service import load_dataframe
from app.services.race_renderer import render_frames
from app.services.social_presets import apply_social_preset
from app.services.style_presets import apply_style_preset
from app.services.video_encoder import RESOLUTION_PIXELS, encode_frames, mix_background_music

_EXPORT_EXTENSIONS = {
    ExportFormat.MP4: ".mp4",
    ExportFormat.GIF: ".gif",
    ExportFormat.PNG_FRAMES: ".zip",
}


class RenderStatus(str, Enum):
    QUEUED = "queued"
    RENDERING = "rendering"
    ENCODING = "encoding"
    DONE = "done"
    FAILED = "failed"


JOBS: dict[str, dict] = {}


def start_render_job(config: RaceConfig, dataset_path: str) -> str:
    job_id = uuid.uuid4().hex[:12]
    JOBS[job_id] = {"status": RenderStatus.QUEUED, "progress": 0, "output_path": None, "error": None}
    thread = threading.Thread(target=_run_render_job, args=(job_id, config, dataset_path), daemon=True)
    thread.start()
    return job_id


def _run_render_job(job_id: str, config: RaceConfig, dataset_path: str) -> None:
    job = JOBS[job_id]
    tmp_frame_dir = os.path.join(RENDERS_DIR, f"_{job_id}_frames")
    try:
        config = apply_social_preset(config)
        config = apply_style_preset(config)

        job["status"] = RenderStatus.RENDERING
        job["progress"] = 5

        df = load_dataframe(dataset_path)
        long_df = build_long_dataframe(df, config.mapping)
        # animation_speed scales the transition duration inversely — a
        # value below 1 stretches each transition out (slow motion), above
        # 1 compresses it. This field previously wasn't wired to anything.
        effective_transition_s = (config.transition_duration_ms / 1000) / max(0.01, config.animation_speed)
        steps = max(1, round(config.fps * effective_transition_s)) if config.smooth_animation else 0
        interpolated = interpolate_frames(long_df, steps_per_transition=steps, interpolation=config.interpolation)
        ranked = compute_frame_rankings(interpolated, config.bar_count, config.sort_direction)
        job["progress"] = 20

        resolution_px = RESOLUTION_PIXELS[config.resolution]
        frame_paths = render_frames(ranked, config, tmp_frame_dir, resolution_px)
        job["progress"] = 80

        job["status"] = RenderStatus.ENCODING
        ext = _EXPORT_EXTENSIONS[config.export_format]
        video_path = os.path.join(RENDERS_DIR, f"{job_id}{ext}")
        encode_frames(frame_paths, config.fps, config.export_format, video_path, config.transparent_background)

        out_path = video_path
        if config.music_asset_id and config.export_format == ExportFormat.MP4:
            music_path = resolve_asset_path(config.music_asset_id)
            if music_path is not None:
                mixed_path = os.path.join(RENDERS_DIR, f"{job_id}_mixed{ext}")
                mix_background_music(video_path, str(music_path), config.music_volume, mixed_path)
                os.remove(video_path)
                out_path = mixed_path

        job["status"] = RenderStatus.DONE
        job["progress"] = 100
        job["output_path"] = out_path
    except Exception as e:
        job["status"] = RenderStatus.FAILED
        job["error"] = str(e)
    finally:
        shutil.rmtree(tmp_frame_dir, ignore_errors=True)
