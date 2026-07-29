"""Encode a sequence of PNG frames into the requested export format.
ffmpeg invocation follows the same defensive pattern already proven
necessary in this repo's other app.py: explicit -pix_fmt yuv420p and
-movflags +faststart, since a plain ffmpeg default output there was
rejected by Windows' Movies & TV app with a generic "unsupported
encoding settings" error that those two flags fixed."""
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
    return shutil.which("ffmpeg") or "ffmpeg"


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
