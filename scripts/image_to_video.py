"""Interactive tool: turn selected images into individual mobile-shorts
videos with background music mixed in.

Pick a source folder, select one or more images from it, pick a destination
folder, and choose a duration (30s or 60s). Produces one MP4 per selected
image, always at 1080x1920 (mobile shorts) regardless of the source image's
own orientation — the image held static for the chosen duration, "Mobile End
video.mp4" (repo root) slid in at the end, and a random track from music/
mixed in over the whole combined duration.

Usage:
    python scripts/image_to_video.py
"""
import glob
import os
import random
import shutil
import subprocess
import tkinter as tk
from tkinter import filedialog

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MUSIC_DIR = os.path.join(BASE_DIR, "music")
MOBILE_END_VIDEO = os.path.join(BASE_DIR, "Mobile End video.mp4")

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".bmp")
RESOLUTION_MOBILE = (1080, 1920)  # 9:16, fixed — shorts only
FPS = 30
XFADE_SECONDS = 1.0  # how long the end video takes to slide across and settle in
# Windows' Movies & TV app is unusually strict — an mp4 ffmpeg produces
# without +faststart (index at the end, the default) plays fine in
# VLC/most players but Movies & TV can refuse it outright with a generic
# "unsupported encoding settings" error. Explicit -pix_fmt yuv420p on the
# output (not just inside a filter) avoids the encoder picking a 10-bit or
# 4:2:2 pixel format from a filter chain, another thing that trips it up.
FASTSTART_ARGS = ["-pix_fmt", "yuv420p", "-movflags", "+faststart"]


def resolve_ffmpeg():
    """Prefer the winget-installed full ffmpeg build over shutil.which()'s
    first PATH hit — some machines have an older/partial ffmpeg earlier on
    PATH (e.g. bundled by an unrelated Python package) that's missing
    filters this project depends on, so check the known-good winget
    install first."""
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
    return "ffmpeg"


FFMPEG_BIN = resolve_ffmpeg()


def ffprobe_duration(path):
    """Probe a media file's duration in seconds via ffprobe (assumed to
    live alongside FFMPEG_BIN, same convention resolve_ffmpeg() relies on)."""
    ffprobe_bin = os.path.join(os.path.dirname(FFMPEG_BIN), "ffprobe.exe")
    if not os.path.isfile(ffprobe_bin):
        ffprobe_bin = "ffprobe"
    out = subprocess.run(
        [ffprobe_bin, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def pick_random_music_track():
    tracks = [
        os.path.join(MUSIC_DIR, f) for f in os.listdir(MUSIC_DIR)
        if f.lower().endswith(".mp3")
    ] if os.path.isdir(MUSIC_DIR) else []
    return random.choice(tracks) if tracks else None


def append_end_video_silent(main_silent_path, end_video_path, out_path, width, height):
    """Slide end_video_path's VIDEO ONLY in from the right over the last
    XFADE_SECONDS of main_silent_path (ffmpeg's xfade "slideleft"
    transition) instead of a hard cut — same technique already proven out
    in this project's other app.py. A no-op copy if end_video_path is
    missing, so a video still renders (just without the outro)."""
    if not os.path.isfile(end_video_path):
        shutil.copy2(main_silent_path, out_path)
        return
    main_duration = ffprobe_duration(main_silent_path)
    offset = max(0.0, main_duration - XFADE_SECONDS)
    cmd = [
        FFMPEG_BIN, "-y",
        "-i", main_silent_path,
        "-i", end_video_path,
        "-filter_complex",
        f"[0:v]fps={FPS}[v0];"
        f"[1:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={FPS}[v1];"
        f"[v0][v1]xfade=transition=slideleft:duration={XFADE_SECONDS}:offset={offset}[outv]",
        "-map", "[outv]",
        "-c:v", "libx264", "-preset", "veryfast",
        *FASTSTART_ARGS,
        out_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def add_looped_music(silent_video_path, total_seconds, out_path):
    """Pick one random track from music/, loop it to cover total_seconds,
    and mux it in as the video's only audio track. Returns the chosen
    track's filename, or None if music/ has no .mp3 files (video keeps no
    audio rather than failing the whole render)."""
    track = pick_random_music_track()
    if not track:
        shutil.copy2(silent_video_path, out_path)
        return None
    cmd = [
        FFMPEG_BIN, "-y",
        "-i", silent_video_path,
        "-stream_loop", "-1", "-i", track,
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy", "-c:a", "aac",
        *FASTSTART_ARGS,
        "-t", str(total_seconds),
        out_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return os.path.basename(track)


def ask_duration(root):
    """Small modal with two buttons — returns 30 or 60, or None if closed
    without a choice."""
    choice = {}

    win = tk.Toplevel(root)
    win.title("Choose video duration")
    win.resizable(False, False)
    win.attributes("-topmost", True)
    win.grab_set()

    tk.Label(win, text="How long should each video be?", padx=24, pady=16).pack()
    button_row = tk.Frame(win, padx=20, pady=12)
    button_row.pack()

    def choose(seconds):
        choice["seconds"] = seconds
        win.destroy()

    tk.Button(button_row, text="30 seconds", width=12, command=lambda: choose(30)).pack(side="left", padx=6)
    tk.Button(button_row, text="60 seconds", width=12, command=lambda: choose(60)).pack(side="left", padx=6)

    root.wait_window(win)
    return choice.get("seconds")


def unique_output_path(dest_dir, stem):
    out_path = os.path.join(dest_dir, f"{stem}.mp4")
    counter = 2
    while os.path.exists(out_path):
        out_path = os.path.join(dest_dir, f"{stem}_{counter}.mp4")
        counter += 1
    return out_path


def build_video(image_path, out_path, duration_s):
    """Mobile-shorts only: static image held for duration_s at
    RESOLUTION_MOBILE (any source orientation scaled/padded to fill that
    vertical frame, never cropped), Mobile End video.mp4 slid in at the
    end, then a random music/ track mixed in over the whole combined
    duration. Returns the chosen track's filename, or None."""
    width, height = RESOLUTION_MOBILE
    scale_pad = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1"
    )
    tmp_dir = out_path + "_tmp"
    os.makedirs(tmp_dir, exist_ok=True)
    try:
        silent_path = os.path.join(tmp_dir, "silent.mp4")
        cmd = [
            FFMPEG_BIN, "-y", "-loop", "1", "-i", image_path,
            "-t", str(duration_s), "-r", str(FPS), "-vf", scale_pad,
            "-c:v", "libx264", "-tune", "stillimage",
            *FASTSTART_ARGS,
            "-an", silent_path,
        ]
        subprocess.run(cmd, check=True, capture_output=True)

        combined_silent_path = os.path.join(tmp_dir, "combined_silent.mp4")
        append_end_video_silent(silent_path, MOBILE_END_VIDEO, combined_silent_path, width, height)
        total_seconds = ffprobe_duration(combined_silent_path)

        return add_looped_music(combined_silent_path, total_seconds, out_path)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def main():
    root = tk.Tk()
    root.withdraw()

    source_folder = filedialog.askdirectory(title="Select source folder containing images")
    if not source_folder:
        print("No source folder selected — aborting.")
        return

    image_paths = filedialog.askopenfilenames(
        title="Select images to convert (multi-select)",
        initialdir=source_folder,
        filetypes=[("Images", " ".join(f"*{ext}" for ext in IMAGE_EXTENSIONS))],
    )
    if not image_paths:
        print("No images selected — aborting.")
        return

    dest_folder = filedialog.askdirectory(title="Select destination folder for videos")
    if not dest_folder:
        print("No destination folder selected — aborting.")
        return

    duration_s = ask_duration(root)
    root.destroy()
    if not duration_s:
        print("No duration chosen — aborting.")
        return

    os.makedirs(dest_folder, exist_ok=True)
    print(f"Rendering {len(image_paths)} video(s) at {duration_s}s each...")
    for image_path in image_paths:
        stem = os.path.splitext(os.path.basename(image_path))[0]
        out_path = unique_output_path(dest_folder, stem)
        try:
            track = build_video(image_path, out_path, duration_s)
            note = f" (music: {track})" if track else " (no music/ tracks found — silent)"
            print(f"[done] {out_path}{note}")
        except subprocess.CalledProcessError as e:
            stderr = e.stderr.decode(errors="replace")[-500:] if e.stderr else str(e)
            print(f"[failed] {image_path}: {stderr}")

    print("All done.")


if __name__ == "__main__":
    main()
