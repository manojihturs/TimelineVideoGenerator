"""Encode a sequence of PNG frames into the requested export format.
ffmpeg invocation follows the same defensive pattern already proven
necessary in this repo's other app.py: explicit -pix_fmt yuv420p and
-movflags +faststart, since a plain ffmpeg default output there was
rejected by Windows' Movies & TV app with a generic "unsupported
encoding settings" error that those two flags fixed."""
import glob
import os
import random
import shutil
import subprocess
import zipfile
from pathlib import Path

from app.models.config import ExportFormat, Resolution

# Applied to every ffmpeg/ffprobe subprocess.run() call below so a hung
# subprocess (bad codec negotiation, a stuck pipe, etc.) raises
# subprocess.TimeoutExpired instead of leaving the render job stuck at
# "rendering"/"encoding" forever — job_manager._run_render_job's except
# Exception clause already catches this and marks the job failed.
FFMPEG_TIMEOUT_S = 600

RESOLUTION_PIXELS: dict[Resolution, tuple[int, int]] = {
    Resolution.HD_1080P: (1920, 1080),
    Resolution.QHD_1440P: (2560, 1440),
    Resolution.UHD_4K: (3840, 2160),
    Resolution.VERTICAL_1080X1920: (1080, 1920),
}


def resolve_ffmpeg() -> str:
    """Prefer the winget-installed full ffmpeg build over whatever
    shutil.which() finds first. Some machines have an older/partial ffmpeg
    binary earlier on PATH (e.g. bundled by an unrelated Python package)
    that's missing filters this project depends on (like xfade, added in
    FFmpeg 4.3) — silently picking that one up causes every "append end
    video" render to fail. The winget full_build is the known-good, fully
    featured install, so check it first and only fall back to PATH lookup
    if it isn't present."""
    local_appdata = os.environ.get("LOCALAPPDATA", "")
    if local_appdata:
        pattern = os.path.join(
            local_appdata, "Microsoft", "WinGet", "Packages",
            "Gyan.FFmpeg_*", "ffmpeg-*-full_build", "bin", "ffmpeg.exe",
        )
        matches = glob.glob(pattern)
        if matches:
            return matches[0]
    found = shutil.which("ffmpeg")
    if found:
        return found
    return "ffmpeg"  # not found anywhere — let subprocess raise a clear error


def encode_frames(
    frame_paths: list[str],
    fps: int,
    export_format: ExportFormat,
    out_path: str,
    transparent_background: bool = False,
) -> str:
    if not frame_paths:
        raise ValueError("No frames to encode")

    frame_dir = os.path.dirname(frame_paths[0])
    pattern = os.path.join(frame_dir, "frame_%05d.png")
    ffmpeg = resolve_ffmpeg()

    if export_format == ExportFormat.PNG_FRAMES:
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in frame_paths:
                zf.write(p, arcname=os.path.basename(p))
        return out_path

    if export_format == ExportFormat.GIF:
        # palette-based two-pass encode for a much better-quality GIF
        # than a naive single-pass conversion
        palette_path = os.path.join(frame_dir, "palette.png")
        try:
            subprocess.run([
                ffmpeg, "-y", "-framerate", str(fps), "-i", pattern,
                "-vf", "palettegen", palette_path,
            ], check=True, capture_output=True, timeout=FFMPEG_TIMEOUT_S)
            subprocess.run([
                ffmpeg, "-y", "-framerate", str(fps), "-i", pattern, "-i", palette_path,
                "-lavfi", "paletteuse", out_path,
            ], check=True, capture_output=True, timeout=FFMPEG_TIMEOUT_S)
        finally:
            # frame_dir currently sits inside a per-job temp dir the caller
            # (job_manager) cleans up wholesale, but clean up explicitly
            # here too rather than relying on that — defense in depth, and
            # consistent with encode_captured_video's palette cleanup below.
            if os.path.exists(palette_path):
                os.remove(palette_path)
        return out_path

    # MP4
    pix_fmt = "yuva420p" if transparent_background else "yuv420p"
    cmd = [
        ffmpeg, "-y", "-framerate", str(fps), "-i", pattern,
        "-pix_fmt", pix_fmt, "-c:v", "libx264" if not transparent_background else "prores_ks",
        "-movflags", "+faststart",
        out_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True, timeout=FFMPEG_TIMEOUT_S)
    return out_path


def probe_duration_seconds(path: str) -> float:
    # Swap only the filename, not the whole path — ffmpeg's own containing
    # directory can legitimately contain "ffmpeg" too (e.g. the WinGet
    # fallback's .../ffmpeg-7.0-full_build/bin/ffmpeg.exe), and a blanket
    # string replace mangles that directory name along with the filename.
    ffmpeg_path = resolve_ffmpeg()
    dirname, basename = os.path.split(ffmpeg_path)
    ffprobe = os.path.join(dirname, basename.replace("ffmpeg", "ffprobe")) if dirname else "ffprobe"
    result = subprocess.run([
        ffprobe, "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", path,
    ], check=True, capture_output=True, text=True, timeout=FFMPEG_TIMEOUT_S)
    return float(result.stdout.strip())


# Playwright starts recording the instant the browser context is created —
# before the page has navigated to the local HTML file and before its
# first draw() call has painted anything, so every capture opens on a
# beat of blank white. How long that gap actually is varies with dataset
# size (a larger embedded frame-data payload takes longer to parse before
# the first draw() call fires), so this trim is deliberately generous —
# a little real animation lost off the very first ~1s is invisible, but
# cutting it short leaves a residual white flash. The intro image
# (job_manager's prepend_intro_image step) covers this gap visually
# regardless, so a slightly-too-generous trim here is a non-issue.
LEAD_TRIM_SECONDS = 1.2


def encode_captured_video(
    webm_path: str,
    fps: int,
    export_format: ExportFormat,
    out_path: str,
    transparent_background: bool = False,
    target_duration_s: float | None = None,
) -> str:
    """Transcodes a Playwright-captured .webm (canvas_renderer.py's output)
    into the requested export format — the equivalent of encode_frames()
    for the CANVAS render engine, whose source is already a video rather
    than a PNG sequence.

    Real-time browser capture drifts from the intended duration (the JS
    animation loop paces itself at 1000/fps per tick, but draw + video-
    encoder overhead per tick isn't free, so actual wall-clock playback
    runs slightly slower than the video's nominal content duration). If
    target_duration_s is given, the remaining clip (after the fixed
    LEAD_TRIM_SECONDS blank-frame trim) is uniformly retimed via setpts to
    land on that exact duration — content-preserving beyond the lead trim
    itself, not cutting the tail off with -t."""
    ffmpeg = resolve_ffmpeg()
    actual_duration_s = probe_duration_seconds(webm_path)
    trim_s = min(LEAD_TRIM_SECONDS, max(0.0, actual_duration_s - 0.1))

    speed_filter = []
    if target_duration_s and target_duration_s > 0:
        remaining_s = max(0.01, actual_duration_s - trim_s)
        multiplier = target_duration_s / remaining_s
        speed_filter = [f"setpts={multiplier}*PTS"]

    if export_format == ExportFormat.GIF:
        # out_path's dirname is the persistent storage/renders/ directory
        # (not a per-job temp dir), so this palette file must be removed
        # explicitly once the paletteuse pass is done — otherwise it leaks
        # permanently, one extra file per canvas-engine GIF export, forever.
        # The try/finally ensures it's still cleaned up if encoding raises
        # (including on a subprocess.TimeoutExpired from the timeout below).
        palette_path = os.path.join(os.path.dirname(out_path), "_palette.png")
        try:
            vf = ",".join(speed_filter + ["palettegen"]) if speed_filter else "palettegen"
            subprocess.run([
                ffmpeg, "-y", "-ss", str(trim_s), "-i", webm_path, "-vf", vf, palette_path,
            ], check=True, capture_output=True, timeout=FFMPEG_TIMEOUT_S)
            vf2 = ",".join(speed_filter) if speed_filter else None
            cmd = [ffmpeg, "-y", "-ss", str(trim_s), "-i", webm_path, "-i", palette_path]
            if vf2:
                cmd += ["-filter_complex", f"[0:v]{vf2}[v];[v][1:v]paletteuse"]
            else:
                cmd += ["-lavfi", "paletteuse"]
            cmd.append(out_path)
            subprocess.run(cmd, check=True, capture_output=True, timeout=FFMPEG_TIMEOUT_S)
        finally:
            if os.path.exists(palette_path):
                os.remove(palette_path)
        return out_path

    pix_fmt = "yuva420p" if transparent_background else "yuv420p"
    vf = ",".join(speed_filter) if speed_filter else None
    cmd = [ffmpeg, "-y", "-ss", str(trim_s), "-i", webm_path]
    if vf:
        cmd += ["-vf", vf]
    cmd += [
        "-r", str(fps), "-pix_fmt", pix_fmt,
        "-c:v", "libx264" if not transparent_background else "prores_ks",
        "-movflags", "+faststart",
        out_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True, timeout=FFMPEG_TIMEOUT_S)
    return out_path


END_VIDEO_XFADE_SECONDS = 1.0


def append_end_video(main_path: str, end_video_path: Path | str, out_path: str, width: int, height: int, fps: int) -> str:
    """Slides end_video_path's VIDEO ONLY in from the right over the last
    END_VIDEO_XFADE_SECONDS of main_path (ffmpeg's xfade "slideleft"
    transition), same technique already proven out in this project's other
    app.py. end_video_path's own audio track is deliberately dropped —
    mix_background_music adds one continuous looped bed over the whole
    combined duration afterward instead, so there's no audio seam at the
    cut. No-ops (copies main_path through) if end_video_path doesn't
    exist, so a missing/not-yet-configured end video never breaks a
    render."""
    end_video_path = Path(end_video_path)
    if not end_video_path.is_file():
        shutil.copy2(main_path, out_path)
        return out_path

    ffmpeg = resolve_ffmpeg()
    main_duration = probe_duration_seconds(main_path)
    offset = max(0.0, main_duration - END_VIDEO_XFADE_SECONDS)
    subprocess.run([
        ffmpeg, "-y",
        "-i", main_path,
        "-i", str(end_video_path),
        "-filter_complex",
        f"[0:v]fps={fps}[v0];"
        f"[1:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}[v1];"
        f"[v0][v1]xfade=transition=slideleft:duration={END_VIDEO_XFADE_SECONDS}:offset={offset}[outv]",
        "-map", "[outv]",
        "-c:v", "libx264", "-preset", "veryfast",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        out_path,
    ], check=True, capture_output=True, timeout=FFMPEG_TIMEOUT_S)
    return out_path


def prepend_intro_image(main_path: str, image_path: Path | str, out_path: str, width: int, height: int, fps: int, duration_s: float) -> str:
    """Holds image_path as a still title card for duration_s, then cuts to
    main_path — covers the canvas engine's blank-white startup gap with a
    deliberate image instead of an accidental flash. No-ops (copies
    main_path through) if image_path doesn't exist, so a missing/not-yet-
    configured intro image never breaks a render."""
    image_path = Path(image_path)
    if not image_path.is_file():
        shutil.copy2(main_path, out_path)
        return out_path

    ffmpeg = resolve_ffmpeg()
    subprocess.run([
        ffmpeg, "-y",
        "-loop", "1", "-t", str(duration_s), "-i", str(image_path),
        "-i", main_path,
        "-filter_complex",
        f"[0:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}[v0];"
        f"[1:v]fps={fps}[v1];"
        f"[v0][v1]concat=n=2:v=1:a=0[outv]",
        "-map", "[outv]",
        "-c:v", "libx264", "-preset", "veryfast",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        out_path,
    ], check=True, capture_output=True, timeout=FFMPEG_TIMEOUT_S)
    return out_path


def pick_random_music(music_dir: Path | str) -> Path | None:
    """One track chosen at random from music_dir's .mp3 files — the same
    'auto background music' behavior as this project's other app.py,
    reused here as the default when a render doesn't specify its own
    music_asset_id. Returns None (silent) if the folder is missing or
    empty rather than failing the render."""
    music_dir = Path(music_dir)
    if not music_dir.is_dir():
        return None
    tracks = list(music_dir.glob("*.mp3"))
    return random.choice(tracks) if tracks else None


def mix_background_music(video_path: str, music_path: str, volume: float, out_path: str) -> str:
    """Loop music_path to cover video_path's full duration (ffmpeg's
    -stream_loop -1 + -shortest, the same looping trick already proven
    out for narration/background-music muxing in this repo's other
    app.py) and mux it in as the video's audio track, scaled to the
    configured volume."""
    ffmpeg = resolve_ffmpeg()
    subprocess.run([
        ffmpeg, "-y",
        "-i", video_path,
        "-stream_loop", "-1", "-i", music_path,
        "-filter_complex", f"[1:a]volume={volume}[music]",
        "-map", "0:v:0", "-map", "[music]",
        "-c:v", "copy", "-c:a", "aac",
        "-shortest",
        "-movflags", "+faststart",
        out_path,
    ], check=True, capture_output=True, timeout=FFMPEG_TIMEOUT_S)
    return out_path
