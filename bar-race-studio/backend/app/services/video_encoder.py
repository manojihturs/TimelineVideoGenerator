"""Encode a sequence of PNG frames into the requested export format.
ffmpeg invocation follows the same defensive pattern already proven
necessary in this repo's other app.py: explicit -pix_fmt yuv420p and
-movflags +faststart, since a plain ffmpeg default output there was
rejected by Windows' Movies & TV app with a generic "unsupported
encoding settings" error that those two flags fixed."""
import glob
import os
import shutil
import subprocess
import zipfile

from app.models.config import ExportFormat, Resolution

RESOLUTION_PIXELS: dict[Resolution, tuple[int, int]] = {
    Resolution.HD_1080P: (1920, 1080),
    Resolution.QHD_1440P: (2560, 1440),
    Resolution.UHD_4K: (3840, 2160),
    Resolution.VERTICAL_1080X1920: (1080, 1920),
}


def resolve_ffmpeg() -> str:
    """Find the ffmpeg binary. shutil.which() covers the normal case, but
    on Windows a long-running process (e.g. this server, started before
    ffmpeg was installed) keeps the PATH it was launched with — a fresh
    shell would see an updated PATH, but this process won't until it's
    restarted. Fall back to searching the winget install location directly
    so newly-installed ffmpeg works without requiring a full machine/process
    restart."""
    found = shutil.which("ffmpeg")
    if found:
        return found
    local_appdata = os.environ.get("LOCALAPPDATA", "")
    if local_appdata:
        pattern = os.path.join(
            local_appdata, "Microsoft", "WinGet", "Packages",
            "Gyan.FFmpeg_*", "ffmpeg-*-full_build", "bin", "ffmpeg.exe",
        )
        matches = glob.glob(pattern)
        if matches:
            return matches[0]
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
        subprocess.run([
            ffmpeg, "-y", "-framerate", str(fps), "-i", pattern,
            "-vf", "palettegen", palette_path,
        ], check=True, capture_output=True)
        subprocess.run([
            ffmpeg, "-y", "-framerate", str(fps), "-i", pattern, "-i", palette_path,
            "-lavfi", "paletteuse", out_path,
        ], check=True, capture_output=True)
        return out_path

    # MP4
    pix_fmt = "yuva420p" if transparent_background else "yuv420p"
    cmd = [
        ffmpeg, "-y", "-framerate", str(fps), "-i", pattern,
        "-pix_fmt", pix_fmt, "-c:v", "libx264" if not transparent_background else "prores_ks",
        "-movflags", "+faststart",
        out_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
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
    ], check=True, capture_output=True, text=True)
    return float(result.stdout.strip())


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
    target_duration_s is given, the whole clip is uniformly retimed via
    setpts to land on that exact duration — content-preserving (nothing
    is trimmed or duplicated, just played back at the corrected speed)
    rather than cutting the tail off with -t."""
    ffmpeg = resolve_ffmpeg()
    speed_filter = []
    if target_duration_s and target_duration_s > 0:
        actual_duration_s = probe_duration_seconds(webm_path)
        if actual_duration_s > 0:
            multiplier = target_duration_s / actual_duration_s
            speed_filter = [f"setpts={multiplier}*PTS"]

    if export_format == ExportFormat.GIF:
        palette_path = os.path.join(os.path.dirname(out_path), "_palette.png")
        vf = ",".join(speed_filter + ["palettegen"]) if speed_filter else "palettegen"
        subprocess.run([
            ffmpeg, "-y", "-i", webm_path, "-vf", vf, palette_path,
        ], check=True, capture_output=True)
        vf2 = ",".join(speed_filter) if speed_filter else None
        cmd = [ffmpeg, "-y", "-i", webm_path, "-i", palette_path]
        if vf2:
            cmd += ["-filter_complex", f"[0:v]{vf2}[v];[v][1:v]paletteuse"]
        else:
            cmd += ["-lavfi", "paletteuse"]
        cmd.append(out_path)
        subprocess.run(cmd, check=True, capture_output=True)
        return out_path

    pix_fmt = "yuva420p" if transparent_background else "yuv420p"
    vf = ",".join(speed_filter) if speed_filter else None
    cmd = [ffmpeg, "-y", "-i", webm_path]
    if vf:
        cmd += ["-vf", vf]
    cmd += [
        "-r", str(fps), "-pix_fmt", pix_fmt,
        "-c:v", "libx264" if not transparent_background else "prores_ks",
        "-movflags", "+faststart",
        out_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return out_path


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
    ], check=True, capture_output=True)
    return out_path
