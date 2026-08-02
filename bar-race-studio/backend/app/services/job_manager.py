"""In-memory background job tracking — same simple pattern as this
repo's other Flask app (a plain dict + daemon thread), appropriate for a
single-process dev server. Swap for Redis/RQ only once concurrent
renders across multiple workers actually matters."""
import os
import re
import shutil
import threading
import uuid
from enum import Enum

from app.api.assets import resolve_asset_path
from app.core.settings import (
    DESKTOP_END_VIDEO, INTRO_IMAGE_SECONDS, MOBILE_END_VIDEO, MUSIC_DIR, RENDERS_DIR,
    WELCOME_IMAGE_DESKTOP, WELCOME_IMAGE_MOBILE,
)
from app.models.config import ExportFormat, RaceConfig, RenderEngine, Resolution
from app.services.canvas_renderer import render_canvas_video
from app.services.dataframe_builder import build_long_dataframe, compute_frame_rankings, interpolate_frames
from app.services.dataset_service import load_dataframe
from app.services.race_renderer import render_frames_parallel
from app.services.social_presets import apply_social_preset
from app.services.style_presets import apply_style_preset
from app.services.video_encoder import (
    RESOLUTION_PIXELS, append_end_video, encode_captured_video, encode_frames,
    mix_background_music, pick_random_music, prepend_intro_image,
)

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

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(text: str) -> str:
    slug = _SLUG_RE.sub("-", text.strip().lower()).strip("-")
    return slug or "bar-race"


def derive_output_filename(config: RaceConfig, ext: str) -> str:
    """The name a downloaded/auto-rendered video actually gets — distinct
    from its on-disk path (which stays job_id-based for collision-safety)
    so "which file is the mobile one" doesn't require opening each video
    to check its aspect ratio."""
    device = "mobile" if config.resolution == Resolution.VERTICAL_1080X1920 else "desktop"
    return f"{_slugify(config.title)}-{device}{ext}"


def start_render_job(config: RaceConfig, dataset_path: str) -> str:
    job_id = uuid.uuid4().hex[:12]
    JOBS[job_id] = {"status": RenderStatus.QUEUED, "progress": 0, "output_path": None,
                     "output_filename": None, "error": None}
    thread = threading.Thread(target=_run_render_job, args=(job_id, config, dataset_path), daemon=True)
    thread.start()
    return job_id


def _run_render_job(job_id: str, config: RaceConfig, dataset_path: str) -> None:
    job = JOBS[job_id]
    tmp_frame_dir = os.path.join(RENDERS_DIR, f"_{job_id}_frames")
    try:
        config = apply_social_preset(config)
        config = apply_style_preset(config)
        # Derived only after preset application — a Studio request that
        # sets social_preset=youtube_shorts without also setting
        # resolution explicitly would otherwise still show the
        # pre-preset (desktop) default here.
        ext = _EXPORT_EXTENSIONS[config.export_format]
        job["output_filename"] = derive_output_filename(config, ext)
        # job_id keeps the on-disk name collision-safe; the friendly part
        # (title + desktop/mobile) makes storage/renders/ itself readable
        # without needing to go through the download endpoint — the
        # auto-render pipeline (folder_watcher) never does.
        disk_name = f"{job_id}-{job['output_filename']}"

        job["status"] = RenderStatus.RENDERING
        job["progress"] = 5

        df = load_dataframe(dataset_path)
        long_df = build_long_dataframe(df, config.mapping)
        # animation_speed scales the transition duration inversely — a
        # value below 1 stretches each transition out (slow motion), above
        # 1 compresses it. This field previously wasn't wired to anything.
        effective_transition_s = (config.transition_duration_ms / 1000) / max(0.01, config.animation_speed)
        steps = max(1, round(config.fps * effective_transition_s)) if config.smooth_animation else 0
        interpolated = interpolate_frames(
            long_df, steps_per_transition=steps,
            sort_direction=config.sort_direction, interpolation=config.interpolation,
        )
        ranked = compute_frame_rankings(interpolated, config.bar_count)
        job["progress"] = 20

        resolution_px = RESOLUTION_PIXELS[config.resolution]
        video_path = os.path.join(RENDERS_DIR, disk_name)

        if config.render_engine == RenderEngine.CANVAS and config.export_format != ExportFormat.PNG_FRAMES:
            # Canvas engine plays the whole animation live and captures it —
            # there's no discrete "80% frames done, now encode" split like the
            # matplotlib path has, so progress just jumps once capture finishes.
            webm_path = render_canvas_video(ranked, config, tmp_frame_dir, resolution_px)
            job["progress"] = 80
            job["status"] = RenderStatus.ENCODING
            n_frames = len(ranked["frame_index"].unique())
            target_duration_s = n_frames / config.fps
            encode_captured_video(webm_path, config.fps, config.export_format, video_path,
                                   config.transparent_background, target_duration_s=target_duration_s)
        else:
            frame_paths = render_frames_parallel(ranked, config, tmp_frame_dir, resolution_px)
            job["progress"] = 80
            job["status"] = RenderStatus.ENCODING
            encode_frames(frame_paths, config.fps, config.export_format, video_path, config.transparent_background)

        out_path = video_path
        if config.export_format == ExportFormat.MP4:
            is_mobile = config.resolution == Resolution.VERTICAL_1080X1920
            end_video = MOBILE_END_VIDEO if is_mobile else DESKTOP_END_VIDEO
            welcome_image = WELCOME_IMAGE_MOBILE if is_mobile else WELCOME_IMAGE_DESKTOP
            with_end_path = os.path.join(RENDERS_DIR, f"{job_id}-with-end-{job['output_filename']}")
            append_end_video(out_path, end_video, with_end_path, resolution_px[0], resolution_px[1], config.fps)
            os.remove(out_path)
            out_path = with_end_path

            with_intro_path = os.path.join(RENDERS_DIR, f"{job_id}-with-intro-{job['output_filename']}")
            prepend_intro_image(out_path, welcome_image, with_intro_path,
                                 resolution_px[0], resolution_px[1], config.fps, INTRO_IMAGE_SECONDS)
            os.remove(out_path)
            out_path = with_intro_path

            # A user-supplied track wins; otherwise fall back to a random
            # pick from MUSIC_DIR so every render gets background music
            # by default, matching this project's other app.py.
            music_path = resolve_asset_path(config.music_asset_id) if config.music_asset_id else None
            if music_path is None:
                music_path = pick_random_music(MUSIC_DIR)
            if music_path is not None:
                mixed_path = os.path.join(RENDERS_DIR, f"{job_id}-mixed-{job['output_filename']}")
                mix_background_music(out_path, str(music_path), config.music_volume, mixed_path)
                os.remove(out_path)
                out_path = mixed_path

        job["status"] = RenderStatus.DONE
        job["progress"] = 100
        job["output_path"] = out_path
    except Exception as e:
        job["status"] = RenderStatus.FAILED
        job["error"] = str(e)
    finally:
        shutil.rmtree(tmp_frame_dir, ignore_errors=True)
