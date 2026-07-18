"""
Reelframe — local project-based video generator.

Architecture (kept intentionally simple, single-process, single-user):
  Flask app.py          -> HTTP API + serves the SPA shell
  projects/<title>/      -> one folder per project, created on demand
      Assets/            -> numbered source images: 1.jpg, 2.jpg, ...
      Thumbnail/          -> user-supplied thumbnail (optional)
      Data/data.csv       -> row N (1-indexed, no header) = text for image N.jpg
      Export/              -> rendered mp4 output lands here
      Narration/           -> optional voiceover audio files
      meta.json            -> project-level settings (currently: category)
  categories.json        -> named item templates (columns + image search
                             suffix), e.g. "Movie" -> [Name, Year, Box
                             office status], "Car" -> [Name, Year, Total
                             sale count]. CRUD via /api/categories.
  jobs (in-memory dict)  -> background render jobs, polled by the UI

Content pipeline (per project, optional, before Generate):
  POST /api/projects/<title>/items with an ordered list of
  {query, row} items fetches one image per item via the official Google
  Custom Search JSON API (requires GOOGLE_CSE_API_KEY / GOOGLE_CSE_CX env
  vars — see README) and writes them to Assets/1.jpg, 2.jpg, ... in the
  given order, then writes `row` values to the matching line of
  Data/data.csv. This is the "auto-fill a project from a category" path;
  images/CSV can still be edited or replaced by hand afterward.

Rendering pipeline (per project, on Generate):
  1. Validate: Assets has >=1 image, Data/data.csv is non-empty.
  2. Sort images numerically (1.jpg, 2.jpg, ...).
  3. Read data.csv; row i (1-indexed) supplies the caption columns for image i.
     Extra images beyond the CSV row count render with no caption.
  4. For each image: build one ffmpeg clip (scale+pad to target resolution/AR,
     drawtext caption burned in), duration = total_duration / image_count.
  5. Concatenate all clips (concat demuxer) into Export/<title>.mp4.

This is deliberately a straight-line pipeline (no queue, no DB) so it stays
easy to read and modify. For heavier use, swap the in-memory `JOBS` dict for
Redis/RQ and the threading.Thread for a real worker.
"""

import csv
import glob
import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid

import numpy as np
import requests
from flask import Flask, jsonify, request, send_from_directory, abort
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_dotenv_local():
    """Load KEY=VALUE lines from .env.local (gitignored) into os.environ,
    without overwriting anything already set in the real environment. Kept
    dependency-free on purpose — this is the only place secrets like
    TMDB_API_KEY / GOOGLE_CSE_API_KEY are allowed to live on disk."""
    path = os.path.join(BASE_DIR, ".env.local")
    if not os.path.isfile(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


_load_dotenv_local()


def resolve_ffmpeg():
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


FFMPEG_BIN = resolve_ffmpeg()

PROJECTS_DIR = os.path.join(BASE_DIR, "projects")
os.makedirs(PROJECTS_DIR, exist_ok=True)

CATEGORIES_PATH = os.path.join(BASE_DIR, "categories.json")
DEFAULT_CATEGORIES = [
    {
        "name": "Movie", "columns": ["Name", "Year of release", "Box office status"],
        "search_suffix": "movie poster", "auto_source": "tmdb_actor",
    },
    {"name": "Car", "columns": ["Name", "Year of release", "Total sale count"], "search_suffix": "car"},
]

# Google Custom Search JSON API (official API, not scraping) — see
# https://developers.google.com/custom-search/v1/overview
GOOGLE_CSE_API_KEY = os.environ.get("GOOGLE_CSE_API_KEY", "")
GOOGLE_CSE_CX = os.environ.get("GOOGLE_CSE_CX", "")
GOOGLE_CSE_ENDPOINT = "https://www.googleapis.com/customsearch/v1"
MAX_ITEMS_PER_FETCH = 50
ALLOWED_IMAGE_CONTENT_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
}

# TMDb (themoviedb.org) — official, free, structured movie database API.
# Used for full "topic -> filmography" automation on the Movie category:
# unlike a search engine, it returns real title/year/budget/revenue/poster
# fields directly, no text scraping or guessing involved.
TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "")
TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w780"
# TMDb's /person/<id>/movie_credits returns the full filmography in one
# call (not paginated), so this is just a runtime/rate-limit safety cap,
# not a real limit on how many movies can be fetched — callers can raise
# it per-request up to HARD_MAX_AUTO_FETCH_MOVIES.
DEFAULT_MAX_AUTO_FETCH_MOVIES = 60
HARD_MAX_AUTO_FETCH_MOVIES = 150

SUBFOLDERS = ["Assets", "Thumbnail", "Data", "Export", "Narration"]

RESOLUTIONS_DESKTOP = {
    "720p": (1280, 720),
    "1080p": (1920, 1080),
    "1440p": (2560, 1440),
    "4K": (3840, 2160),
}
RESOLUTION_MOBILE = (1080, 1920)  # 9:16, fixed
MOBILE_MAX_SECONDS = 60

THUMB_SIZES = {
    "desktop": (1280, 720),   # standard YouTube/16:9 thumbnail
    "mobile": (1080, 1920),   # Reels/Shorts/Stories cover
}
AUDIO_EXTS = (".mp3", ".wav", ".m4a", ".aac", ".ogg")
FONT_HEADLINE = os.path.join(BASE_DIR, "static", "fonts", "DejaVuSansCondensed-Bold.ttf")

app = Flask(__name__, static_folder="static", template_folder="templates")

# job_id -> {status, progress, message, output_path}
JOBS = {}


# --------------------------------------------------------------------------
# categories
# --------------------------------------------------------------------------

def load_categories():
    if not os.path.isfile(CATEGORIES_PATH):
        save_categories(DEFAULT_CATEGORIES)
        return list(DEFAULT_CATEGORIES)
    with open(CATEGORIES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_categories(categories):
    with open(CATEGORIES_PATH, "w", encoding="utf-8") as f:
        json.dump(categories, f, indent=2)


def get_category(name):
    for c in load_categories():
        if c["name"] == name:
            return c
    return None


def project_meta_path(title):
    return os.path.join(project_path(title), "meta.json")


def load_project_meta(title):
    p = project_meta_path(title)
    if not os.path.isfile(p):
        return {}
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def save_project_meta(title, meta):
    with open(project_meta_path(title), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def safe_title(title: str) -> str:
    """Turn a user-entered title into a filesystem-safe folder name."""
    title = title.strip()
    title = re.sub(r"[^A-Za-z0-9 _-]+", "", title)
    title = re.sub(r"\s+", " ", title).strip()
    return title


def project_path(title: str) -> str:
    return os.path.join(PROJECTS_DIR, title)


def list_projects():
    out = []
    if not os.path.isdir(PROJECTS_DIR):
        return out
    for name in sorted(os.listdir(PROJECTS_DIR)):
        p = project_path(name)
        if os.path.isdir(p):
            out.append(project_summary(name))
    return out


def numbered_images(assets_dir):
    """Return image paths sorted by their leading number: 1.jpg, 2.jpg, ..."""
    files = []
    if not os.path.isdir(assets_dir):
        return files
    for f in os.listdir(assets_dir):
        m = re.match(r"^(\d+)\.(jpe?g|png)$", f, re.IGNORECASE)
        if m:
            files.append((int(m.group(1)), os.path.join(assets_dir, f)))
    files.sort(key=lambda x: x[0])
    return files


def csv_rows(data_csv_path):
    rows = {}
    if not os.path.isfile(data_csv_path):
        return rows
    with open(data_csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        for i, row in enumerate(reader, start=1):
            rows[i] = [c.strip() for c in row if c.strip() != ""]
    return rows


def csv_is_empty(data_csv_path):
    if not os.path.isfile(data_csv_path):
        return True
    if os.path.getsize(data_csv_path) == 0:
        return True
    rows = csv_rows(data_csv_path)
    return len(rows) == 0


def narration_files(project_root):
    d = os.path.join(project_root, "Narration")
    if not os.path.isdir(d):
        return []
    files = [f for f in os.listdir(d) if f.lower().endswith(AUDIO_EXTS)]
    files.sort()
    return [os.path.join(d, f) for f in files]


def project_summary(title):
    p = project_path(title)
    assets_dir = os.path.join(p, "Assets")
    data_csv = os.path.join(p, "Data", "data.csv")
    images = numbered_images(assets_dir)
    folders_ok = all(os.path.isdir(os.path.join(p, sf)) for sf in SUBFOLDERS)
    narr = narration_files(p)
    thumb_dir = os.path.join(p, "Thumbnail")
    meta = load_project_meta(title)
    return {
        "title": title,
        "category": meta.get("category"),
        "folders_ok": folders_ok,
        "asset_count": len(images),
        "asset_numbers": [num for num, _ in images],
        "assets_ok": len(images) > 0,
        "csv_ok": not csv_is_empty(data_csv),
        "narration_count": len(narr),
        "narration_ok": len(narr) > 0,
        "ready": folders_ok and len(images) > 0 and not csv_is_empty(data_csv),
        "exports": sorted(
            f for f in os.listdir(os.path.join(p, "Export"))
            if f.lower().endswith(".mp4") and os.path.isfile(os.path.join(p, "Export", f))
        ) if os.path.isdir(os.path.join(p, "Export")) else [],
        "thumbnails": sorted(
            f for f in os.listdir(thumb_dir) if f.lower().endswith((".jpg", ".jpeg", ".png"))
        ) if os.path.isdir(thumb_dir) else [],
    }


POSTER_BG_PALETTE = ["#F4D35E", "#3EC6B6", "#F2B4C4", "#8ECAE6", "#C9B6E4"]
BAND_BG_PALETTE = ["#F2B4C4", "#F4D35E", "#3EC6B6", "#C9B6E4"]
VERDICT_COLORS = {
    "FLOP": "#E4372B", "DISASTER": "#E4372B", "AVERAGE": "#E08E1C",
    "HIT": "#2E8B33", "SUPERHIT": "#1F7A34", "BLOCKBUSTER": "#1F7A34",
    "SUCCESS": "#2E8B33",
}


def cover_fit(img, box_w, box_h):
    """Scale+crop to fill box_w x box_h exactly — 'best fit' with no empty
    margin, matching the reference template's edge-to-edge poster crop."""
    src_w, src_h = img.size
    scale = max(box_w / src_w, box_h / src_h)
    new_w, new_h = max(1, int(src_w * scale)), max(1, int(src_h * scale))
    img = img.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - box_w) // 2
    top = (new_h - box_h) // 2
    return img.crop((left, top, left + box_w, top + box_h))


def add_poster_texture(canvas, x0, y0, box_w, box_h, base_color):
    """Bake a subtle diagonal stripe texture into the poster-zone background.
    It reads as static here, but since the whole strip later scrolls
    horizontally, this texture animates for free — a cheap, tasteful
    'moving background' without extra render passes."""
    tex = Image.new("RGB", (box_w, box_h), base_color)
    td = ImageDraw.Draw(tex)
    stripe_w = max(18, box_w // 26)
    light = tuple(min(255, c + 22) for c in ImageColor_to_rgb(base_color))
    x = -box_h
    while x < box_w:
        td.line([(x, box_h), (x + box_h, 0)], fill=light, width=stripe_w // 2)
        x += stripe_w
    canvas.paste(tex, (x0, y0))


def ImageColor_to_rgb(hex_color):
    from PIL import ImageColor
    return ImageColor.getrgb(hex_color)


def fit_font_to_width(text, max_width, start_size, font_path, min_size=18):
    size = start_size
    font = ImageFont.truetype(font_path, size)
    tmp = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    while size > min_size and tmp.textlength(text, font=font) > max_width:
        size -= 3
        font = ImageFont.truetype(font_path, size)
    return font


def build_recap_frame(image_path, columns, width, height, card_index, badge_number=None):
    """Compose one 'recap card': source image cropped to best-fill a bold
    color panel up top, stacked colored bands below it — one per CSV
    column — each with bold, white-stroked, auto-fit text. Verdict-style
    words (FLOP/HIT/BLOCKBUSTER/...) get their own accent color. Returns
    a PIL Image (card_index only affects the poster panel's color, so
    consecutive cards in a scroll don't look identical). When badge_number
    is set, a small numbered tag is drawn over the poster's top-left corner
    — used when several cards share one screen (see CARDS_PER_SCREEN)."""
    poster_bg = POSTER_BG_PALETTE[card_index % len(POSTER_BG_PALETTE)]
    canvas = Image.new("RGB", (width, height), "#000000")

    poster_zone_h = int(height * 0.52)
    add_poster_texture(canvas, 0, 0, width, poster_zone_h, poster_bg)

    src = Image.open(image_path).convert("RGB")
    fitted = cover_fit(src, width, poster_zone_h)  # best-fit: fill, no empty margin
    canvas.paste(fitted, (0, 0))

    if badge_number is not None:
        draw_badge = ImageDraw.Draw(canvas)
        badge_size = max(28, int(width * 0.16))
        badge_text = str(badge_number).zfill(2)
        draw_badge.rectangle([0, 0, badge_size, badge_size], fill="#1D4ED8")
        badge_font = fit_font_to_width(badge_text, badge_size * 0.7, int(badge_size * 0.6), FONT_HEADLINE, min_size=12)
        bb = draw_badge.textbbox((0, 0), badge_text, font=badge_font)
        bw, bh = bb[2] - bb[0], bb[3] - bb[1]
        draw_badge.text(
            ((badge_size - bw) // 2 - bb[0], (badge_size - bh) // 2 - bb[1]),
            badge_text, font=badge_font, fill="#FFFFFF",
        )

    columns = [c for c in columns if c.strip()][:6] or ["—"]
    band_zone_h = height - poster_zone_h
    band_h = band_zone_h // len(columns)

    draw = ImageDraw.Draw(canvas)
    pad_x = int(width * 0.06)

    for i, text in enumerate(columns):
        band_color = BAND_BG_PALETTE[i % len(BAND_BG_PALETTE)]
        y0 = poster_zone_h + i * band_h
        y1 = y0 + band_h if i < len(columns) - 1 else height
        draw.rectangle([0, y0, width, y1], fill=band_color)

        upper = text.strip().upper()
        text_fill = VERDICT_COLORS.get(upper, "#141414")
        font = fit_font_to_width(text.upper(), width - pad_x * 2, int(band_h * 0.55), FONT_HEADLINE)
        bbox = draw.textbbox((0, 0), text.upper(), font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        tx = (width - tw) // 2
        ty = y0 + (band_h - th) // 2 - bbox[1] if i < len(columns) - 1 else (y0 + y1) // 2 - th // 2 - bbox[1]
        draw.text(
            (tx, ty), text.upper(), font=font, fill=text_fill,
            stroke_width=max(2, int(band_h * 0.045)), stroke_fill="#FFFFFF",
        )

    return canvas


CARDS_PER_SCREEN = 3


def build_scroll_strip(objects, width, height, gap, cards_per_screen=CARDS_PER_SCREEN):
    """Pack `cards_per_screen` cards side by side into one full-width
    'screen' (narrower columns, numbered badges — matching a multi-up
    recap layout), then lay screens left-to-right with a fixed gap between
    them into one wide image ready to be panned across. Packing several
    cards per screen instead of one keeps the total strip width — and so
    the per-frame crop/encode cost — roughly cards_per_screen times
    smaller for the same item count."""
    col_w = max(1, width // cards_per_screen)
    n_screens = -(-len(objects) // cards_per_screen)  # ceil
    strip_w = n_screens * width + (n_screens - 1) * gap
    strip = Image.new("RGB", (strip_w, height), "#000000")  # matches the in-screen divider color

    divider_w = max(2, int(col_w * 0.006))
    strip_draw = ImageDraw.Draw(strip)

    x = 0
    for screen_idx in range(n_screens):
        group = objects[screen_idx * cards_per_screen: (screen_idx + 1) * cards_per_screen]
        cx = x
        for i, (num, img_path, columns) in enumerate(group):
            card_index = screen_idx * cards_per_screen + i
            col = build_recap_frame(img_path, columns, col_w, height, card_index, badge_number=card_index + 1)
            strip.paste(col, (cx, 0))
            if i > 0:
                strip_draw.rectangle([cx - divider_w, 0, cx, height], fill="#000000")
            cx += col_w
        x += width + gap

    return strip, strip_w


FPS = 30


def render_scroll_video(strip_path, width, height, total_seconds, out_path):
    """Pan a constant-speed crop window right-to-left across the strip —
    the scroll IS the transition, so cards are revealed one after another
    with no cuts.

    The crop is done in Python (numpy slicing) and streamed to ffmpeg as
    raw frames on stdin, rather than asking ffmpeg's own crop filter to
    pan across a `-loop`ed single huge image. That combination turned out
    to cost ~150ms/frame regardless of source format (PNG or raw) — ffmpeg
    appears to re-copy the entire multi-thousand-pixel-wide source frame
    on every single output frame rather than treating it as a cheap,
    cached view to slice from. A numpy view + stdin pipe sidesteps that
    entirely: measured ~30x faster on a 60-card strip."""
    img = Image.open(strip_path).convert("RGB")
    arr = np.asarray(img)
    strip_w = arr.shape[1]
    travel = max(1, strip_w - width)
    speed = travel / total_seconds  # px/sec
    n_frames = int(total_seconds * FPS)

    cmd = [
        FFMPEG_BIN, "-y",
        "-f", "rawvideo", "-pixel_format", "rgb24", "-video_size", f"{width}x{height}",
        "-framerate", str(FPS), "-i", "-",
        "-t", str(total_seconds),
        "-pix_fmt", "yuv420p",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-threads", "0",
        out_path,
    ]
    # stderr goes to a file, not a PIPE: ffmpeg's per-frame stderr logging
    # over 18000+ frames can exceed the OS pipe buffer, and since nothing
    # reads a PIPE while this loop is busy writing stdin, ffmpeg blocks on
    # its own stderr write and stdin stalls right along with it — a
    # deadlock that looks exactly like "very slow", not like a hang.
    stderr_path = out_path + ".stderr.log"
    with open(stderr_path, "wb") as stderr_f:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=stderr_f)
        try:
            for i in range(n_frames):
                x = min(int(i / FPS * speed), travel)
                proc.stdin.write(arr[:, x:x + width, :].tobytes())
            proc.stdin.close()
            proc.wait()
        finally:
            if proc.stdin and not proc.stdin.closed:
                proc.stdin.close()
    if proc.returncode != 0:
        with open(stderr_path, "rb") as f:
            stderr_data = f.read()
        os.remove(stderr_path)
        raise subprocess.CalledProcessError(proc.returncode, cmd, stderr=stderr_data)
    os.remove(stderr_path)


def build_narration_track(audio_paths, out_path):
    """Concatenate one or more Narration/ audio files (any mix of formats)
    into a single track using filter_complex, which tolerates mismatched
    codecs/sample rates better than the concat demuxer."""
    if len(audio_paths) == 1:
        cmd = [FFMPEG_BIN, "-y", "-i", audio_paths[0], "-c:a", "aac", out_path]
        subprocess.run(cmd, check=True, capture_output=True)
        return

    inputs = []
    for a in audio_paths:
        inputs += ["-i", a]
    n = len(audio_paths)
    filter_str = "".join(f"[{i}:a]" for i in range(n)) + f"concat=n={n}:v=0:a=1[aout]"
    cmd = [FFMPEG_BIN, "-y", *inputs, "-filter_complex", filter_str, "-map", "[aout]", "-c:a", "aac", out_path]
    subprocess.run(cmd, check=True, capture_output=True)


def mux_narration(silent_video_path, narration_path, total_seconds, out_path):
    """Attach narration as the audio track, looping it if shorter than the
    video and trimming if longer, so the final file always runs exactly
    total_seconds."""
    cmd = [
        FFMPEG_BIN, "-y",
        "-i", silent_video_path,
        "-stream_loop", "-1", "-i", narration_path,
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy", "-c:a", "aac",
        "-t", str(total_seconds),
        out_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def cover_resize(img, target_w, target_h):
    """Resize+crop to fill target size exactly (no letterboxing) — a
    thumbnail should read at a glance, so it fills the whole frame."""
    src_w, src_h = img.size
    src_ratio = src_w / src_h
    tgt_ratio = target_w / target_h
    if src_ratio > tgt_ratio:
        new_h = target_h
        new_w = max(target_w, int(new_h * src_ratio))
    else:
        new_w = target_w
        new_h = max(target_h, int(new_w / src_ratio))
    img = img.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    return img.crop((left, top, left + target_w, top + target_h))


def wrap_text(draw, text, font, max_width, max_lines=2):
    words = text.upper().split()
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if draw.textlength(trial, font=font) <= max_width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines[:max_lines]


def make_thumbnail(src_path, headline, size, out_path):
    """Build a punchy, social-media-style thumbnail: cover-cropped source
    image, boosted contrast/saturation, a bottom scrim for legibility, a
    bold stroked headline, an accent bar, and a play-button cue so it reads
    as 'video' at a glance."""
    w, h = size
    img = Image.open(src_path).convert("RGB")
    img = cover_resize(img, w, h)

    img = ImageEnhance.Color(img).enhance(1.35)
    img = ImageEnhance.Contrast(img).enhance(1.15)
    img = ImageEnhance.Brightness(img).enhance(1.03)

    # soft vignette so the eye settles toward center/text, not the edges
    vignette = Image.new("L", (w, h), 0)
    vd = ImageDraw.Draw(vignette)
    vd.ellipse([-w * 0.25, -h * 0.25, w * 1.25, h * 1.25], fill=255)
    vignette = vignette.filter(ImageFilter.GaussianBlur(int(w * 0.08)))
    dark = Image.new("RGB", (w, h), (0, 0, 0))
    img = Image.composite(img, dark, vignette)

    # bottom gradient scrim behind the headline
    scrim_h = int(h * 0.46)
    gradient = Image.new("L", (1, scrim_h), 0)
    for y in range(scrim_h):
        gradient.putpixel((0, y), int(255 * (y / scrim_h) ** 1.6))
    gradient = gradient.resize((w, scrim_h))
    black = Image.new("RGB", (w, scrim_h), (5, 6, 8))
    scrim_region = Image.composite(black, img.crop((0, h - scrim_h, w, h)), gradient)
    img.paste(scrim_region, (0, h - scrim_h))

    draw = ImageDraw.Draw(img)
    pad = int(w * 0.055)
    max_text_width = w - pad * 2
    font_size = int(h * 0.115)
    font = ImageFont.truetype(FONT_HEADLINE, font_size)
    lines = wrap_text(draw, headline, font, max_text_width)
    while len(lines) > 2 and font_size > 24:
        font_size -= 4
        font = ImageFont.truetype(FONT_HEADLINE, font_size)
        lines = wrap_text(draw, headline, font, max_text_width)

    line_height = int(font_size * 1.08)
    total_text_h = line_height * max(1, len(lines))
    y = h - pad - total_text_h

    for line in lines:
        draw.text(
            (pad, y), line, font=font, fill=(255, 255, 255),
            stroke_width=max(2, font_size // 14), stroke_fill=(10, 11, 14),
        )
        y += line_height

    amber = (232, 163, 61)
    bar_y = h - pad - total_text_h - int(h * 0.02)
    draw.rectangle([pad, bar_y, pad + int(w * 0.09), bar_y + 6], fill=amber)

    # play-button cue so it reads as video content, not a plain photo
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    r = int(min(w, h) * 0.09)
    cx, cy = w // 2, int(h * 0.4)
    od.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 255, 255, 230), outline=(10, 11, 14, 255), width=4)
    tw = r * 0.8
    od.polygon(
        [(cx - tw * 0.35, cy - tw * 0.55), (cx - tw * 0.35, cy + tw * 0.55), (cx + tw * 0.65, cy)],
        fill=(20, 23, 28, 255),
    )
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

    img.save(out_path, quality=92)


def request_with_retries(method, url, max_attempts=5, **kwargs):
    """requests.request wrapper that retries transient connection failures
    (reset/timeout) with a short backoff. Real network calls to third-party
    APIs fail intermittently; a multi-step fetch job (search + per-item
    detail + image download) has many chances to hit one, so this keeps a
    whole job from dying on a single blip."""
    last_exc = None
    for attempt in range(1, max_attempts + 1):
        try:
            return requests.request(method, url, **kwargs)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            last_exc = e
            if attempt < max_attempts:
                time.sleep(min(1.0 * (2 ** (attempt - 1)), 8.0))
    raise last_exc


def google_image_search(query, timeout=15):
    """Look up the top image result for `query` via the official Google
    Custom Search JSON API (not scraping — requires an API key + Search
    Engine ID configured for Image search). Returns a direct image URL or
    None if no result / not configured."""
    if not GOOGLE_CSE_API_KEY or not GOOGLE_CSE_CX:
        raise RuntimeError(
            "Google Custom Search is not configured. Set GOOGLE_CSE_API_KEY "
            "and GOOGLE_CSE_CX environment variables."
        )
    params = {
        "key": GOOGLE_CSE_API_KEY,
        "cx": GOOGLE_CSE_CX,
        "q": query,
        "searchType": "image",
        "num": 1,
        "safe": "active",
    }
    resp = request_with_retries("GET", GOOGLE_CSE_ENDPOINT, params=params, timeout=timeout)
    resp.raise_for_status()
    items = resp.json().get("items") or []
    if not items:
        return None
    return items[0].get("link")


def download_image(url, dest_no_ext, timeout=20):
    """Download `url` to dest_no_ext.<ext>, ext chosen from the response's
    Content-Type. Rejects non-image responses. Returns the final path."""
    resp = request_with_retries("GET", url, timeout=timeout, stream=True)
    resp.raise_for_status()
    content_type = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
    ext = ALLOWED_IMAGE_CONTENT_TYPES.get(content_type)
    if not ext:
        raise RuntimeError(f"Result at {url} was not a jpg/png image (got {content_type or 'unknown'}).")
    dest_path = f"{dest_no_ext}.{ext}"
    with open(dest_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=65536):
            f.write(chunk)
    return dest_path


def tmdb_get(path, params=None, timeout=15):
    if not TMDB_API_KEY:
        raise RuntimeError(
            "TMDb is not configured. Set the TMDB_API_KEY environment variable "
            "(free key from https://www.themoviedb.org/settings/api)."
        )
    params = dict(params or {})
    params["api_key"] = TMDB_API_KEY
    resp = request_with_retries("GET", f"{TMDB_BASE}{path}", params=params, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def compute_verdict(budget, revenue):
    """Classify a movie's commercial result from budget vs revenue —
    the same structured signal box-office sites use, so this is a real
    computed verdict, not a guess."""
    if not budget or not revenue:
        return "—"
    ratio = revenue / budget
    if ratio < 1:
        return "FLOP"
    if ratio < 2:
        return "AVERAGE"
    if ratio < 4:
        return "HIT"
    return "BLOCKBUSTER"


def run_auto_fetch_movie_job(job_id, title, topic, max_movies=DEFAULT_MAX_AUTO_FETCH_MOVIES):
    """Given an actor's name, pull their full filmography from TMDb —
    title, release year, poster, and a computed budget-vs-revenue verdict
    — sort by year ascending, and populate Assets/<n>.jpg + Data/data.csv.
    No manual data entry: TMDb is a structured database, not a search
    engine, so every field comes back as real data, not scraped text.

    Resumable: a fetch is ~2x(N) HTTPS round trips (movie detail + poster
    per item), and a single transient connection reset anywhere in that
    sequence used to mean starting over from item 1. State (which movie ids
    were already written, in what order) is persisted to a small JSON file
    in the project; a retry for the same topic/list picks up where the
    last attempt left off instead of redoing completed work."""
    job = JOBS[job_id]
    try:
        p = project_path(title)
        assets_dir = os.path.join(p, "Assets")
        data_csv = os.path.join(p, "Data", "data.csv")
        state_path = os.path.join(p, "Data", ".autofetch_state.json")

        job["progress"] = 3
        job["message"] = f'Looking up "{topic}" on TMDb'
        search = tmdb_get("/search/person", {"query": topic})
        results = search.get("results") or []
        if not results:
            raise RuntimeError(f'No TMDb match found for "{topic}".')
        person = results[0]

        job["progress"] = 8
        job["message"] = f"Fetching filmography for {person['name']}"
        credits = tmdb_get(f"/person/{person['id']}/movie_credits")
        cast = credits.get("cast") or []

        # de-dupe by movie id, keep only movies with a known release date
        # AND a poster — a handful of minor/uncredited roles have neither,
        # and one missing poster shouldn't sink an otherwise-good fetch,
        # so those are skipped rather than failing the job.
        seen = set()
        movies = []
        for c in cast:
            if c["id"] in seen or not c.get("release_date") or not c.get("poster_path"):
                continue
            seen.add(c["id"])
            movies.append(c)
        movies.sort(key=lambda m: m["release_date"])
        movies = movies[:max_movies]

        if not movies:
            raise RuntimeError(f"No dated, posterized movie credits found for {person['name']}.")

        movie_ids = [m["id"] for m in movies]
        resume_from = 0  # 0-indexed count of items already completed
        rows = []
        state = None
        if os.path.isfile(state_path):
            try:
                with open(state_path, "r", encoding="utf-8") as f:
                    state = json.load(f)
            except (OSError, ValueError):
                state = None
        if state and state.get("topic") == topic and state.get("movie_ids") == movie_ids:
            resume_from = state.get("completed", 0)
            rows = state.get("rows", [])
            job["message"] = f"Resuming from item {resume_from + 1}/{len(movies)}"
        else:
            for _, old_path in numbered_images(assets_dir):
                os.remove(old_path)

        def save_state(completed):
            with open(state_path, "w", encoding="utf-8") as f:
                json.dump({"topic": topic, "movie_ids": movie_ids, "completed": completed, "rows": rows}, f)

        total = len(movies)
        for i, m in enumerate(movies, start=1):
            if i <= resume_from:
                continue
            job["progress"] = 8 + int((i - 1) / total * 85)
            job["message"] = f"Fetching {i}/{total}: {m['title']}"

            detail = tmdb_get(f"/movie/{m['id']}")
            year = (m.get("release_date") or "")[:4]
            verdict = compute_verdict(detail.get("budget"), detail.get("revenue"))

            download_image(f"{TMDB_IMAGE_BASE}{m['poster_path']}", os.path.join(assets_dir, str(i)))

            rows.append([m["title"], year, verdict])
            save_state(i)

        with open(data_csv, "w", newline="", encoding="utf-8-sig") as f:
            csv.writer(f).writerows(rows)
        if os.path.isfile(state_path):
            os.remove(state_path)

        job["status"] = "done"
        job["progress"] = 100
        job["message"] = f"Fetched {total} movie(s) for {person['name']}"
    except Exception as e:
        job["status"] = "error"
        job["message"] = str(e)


def run_fetch_items_job(job_id, title, items, category_name):
    """For each item (in the given order): search+download one image into
    Assets/<n>.<ext>, then write all rows into Data/data.csv so row n lines
    up with image n — same convention the render pipeline expects."""
    job = JOBS[job_id]
    try:
        p = project_path(title)
        assets_dir = os.path.join(p, "Assets")
        data_csv = os.path.join(p, "Data", "data.csv")

        category = get_category(category_name) if category_name else None
        suffix = (category or {}).get("search_suffix", "")

        # clear any existing numbered images so re-fetching doesn't leave stale files
        for _, old_path in numbered_images(assets_dir):
            os.remove(old_path)

        total = len(items)
        rows = []
        for i, item in enumerate(items, start=1):
            job["progress"] = int((i - 1) / total * 90)
            job["message"] = f"Fetching image {i}/{total}: {item['query']}"

            query = item["query"] if not suffix else f"{item['query']} {suffix}"
            image_url = google_image_search(query)
            if not image_url:
                raise RuntimeError(f"No image result found for \"{item['query']}\".")
            download_image(image_url, os.path.join(assets_dir, str(i)))

            rows.append(item["row"])

        with open(data_csv, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerows(rows)

        job["status"] = "done"
        job["progress"] = 100
        job["message"] = f"Fetched {total} item(s)"
    except Exception as e:
        job["status"] = "error"
        job["message"] = str(e)


def run_render_job(job_id, title, device, width, height, total_seconds, max_items=None):
    job = JOBS[job_id]
    try:
        p = project_path(title)
        assets_dir = os.path.join(p, "Assets")
        export_dir = os.path.join(p, "Export")
        data_csv = os.path.join(p, "Data", "data.csv")

        images_by_num = dict(numbered_images(assets_dir))
        rows = csv_rows(data_csv)
        # one object per CSV row that has a matching numbered image —
        # the CSV is the source of truth for what gets built
        row_nums = sorted(rows.keys())
        objects = [(n, images_by_num[n], rows[n]) for n in row_nums if n in images_by_num]

        if max_items and len(objects) > max_items:
            # keep the LAST max_items rows, not the first — rows are in
            # their original order (e.g. chronological ascending for an
            # auto-fetched filmography), so this is "the most recent N",
            # still shown oldest-to-newest, useful for a short mobile cut
            # that can't fit every item at a readable pace
            objects = objects[-max_items:]

        if not objects:
            raise RuntimeError(
                "No CSV rows matched a numbered image. Make sure row 1 has a "
                "1.jpg, row 2 has a 2.jpg, etc."
            )

        tmp_dir = os.path.join(export_dir, f"_tmp_{job_id}")
        os.makedirs(tmp_dir, exist_ok=True)

        try:
            job["progress"] = 10
            job["message"] = f"Building {len(objects)} card(s)"
            # match the thin in-screen column dividers so the pan doesn't
            # show a noticeably wider gap between screens than it does
            # between the cards within one screen
            gap = max(2, int((width // CARDS_PER_SCREEN) * 0.006))
            strip, strip_w = build_scroll_strip(objects, width, height, gap)
            strip_path = os.path.join(tmp_dir, "strip.png")
            strip.save(strip_path)

            job["progress"] = 55
            job["message"] = "Rendering scroll"
            out_name = f"{title}_{device}.mp4"
            final_out_path = os.path.join(export_dir, out_name)
            # render into the temp dir and only move the finished file into
            # Export/ at the very end — otherwise the Exports list (which
            # just lists what's in that folder) shows a partial, unplayable
            # file as "downloadable" while ffmpeg is still writing it.
            tmp_out_path = os.path.join(tmp_dir, out_name)

            narr = narration_files(p)
            if narr:
                silent_path = os.path.join(tmp_dir, "silent.mp4")
                render_scroll_video(strip_path, width, height, total_seconds, silent_path)

                job["progress"] = 90
                job["message"] = "Mixing narration"
                narration_track = os.path.join(tmp_dir, "narration.m4a")
                build_narration_track(narr, narration_track)
                mux_narration(silent_path, narration_track, total_seconds, tmp_out_path)
            else:
                render_scroll_video(strip_path, width, height, total_seconds, tmp_out_path)

            os.replace(tmp_out_path, final_out_path)

            job["status"] = "done"
            job["progress"] = 100
            job["message"] = "Export complete"
            job["output_path"] = out_name
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
    except subprocess.CalledProcessError as e:
        job["status"] = "error"
        job["message"] = "ffmpeg failed: " + (e.stderr.decode(errors="ignore")[-400:] if e.stderr else str(e))
    except Exception as e:
        job["status"] = "error"
        job["message"] = str(e)


# --------------------------------------------------------------------------
# routes
# --------------------------------------------------------------------------

@app.route("/")
def index():
    from flask import render_template
    return render_template("index.html")


@app.route("/api/projects", methods=["GET"])
def api_list_projects():
    return jsonify(list_projects())


@app.route("/api/projects", methods=["POST"])
def api_create_project():
    data = request.get_json(force=True) or {}
    raw_title = data.get("title", "")
    title = safe_title(raw_title)
    if not title:
        return jsonify({"error": "Title is required."}), 400

    p = project_path(title)
    if os.path.isdir(p):
        return jsonify({"error": f'A project named "{title}" already exists.'}), 409

    for sf in SUBFOLDERS:
        os.makedirs(os.path.join(p, sf), exist_ok=True)
    # empty data.csv, ready to be filled in
    open(os.path.join(p, "Data", "data.csv"), "a").close()

    return jsonify(project_summary(title)), 201


@app.route("/api/categories", methods=["GET"])
def api_list_categories():
    return jsonify(load_categories())


@app.route("/api/categories", methods=["POST"])
def api_create_category():
    data = request.get_json(force=True) or {}
    name = (data.get("name") or "").strip()
    columns = [c.strip() for c in (data.get("columns") or []) if c.strip()]
    search_suffix = (data.get("search_suffix") or "").strip()

    if not name:
        return jsonify({"error": "Category name is required."}), 400
    if not columns:
        return jsonify({"error": "At least one column is required."}), 400

    categories = load_categories()
    if any(c["name"].lower() == name.lower() for c in categories):
        return jsonify({"error": f'A category named "{name}" already exists.'}), 409

    category = {"name": name, "columns": columns, "search_suffix": search_suffix}
    categories.append(category)
    save_categories(categories)
    return jsonify(category), 201


@app.route("/api/categories/<name>", methods=["DELETE"])
def api_delete_category(name):
    categories = load_categories()
    remaining = [c for c in categories if c["name"].lower() != name.lower()]
    if len(remaining) == len(categories):
        abort(404)
    save_categories(remaining)
    return jsonify({"deleted": name})


@app.route("/api/projects/<title>/category", methods=["POST"])
def api_set_project_category(title):
    if not os.path.isdir(project_path(title)):
        abort(404)
    data = request.get_json(force=True) or {}
    category_name = (data.get("category") or "").strip()
    if category_name and not get_category(category_name):
        return jsonify({"error": f'Unknown category "{category_name}".'}), 400

    meta = load_project_meta(title)
    meta["category"] = category_name or None
    save_project_meta(title, meta)
    return jsonify(project_summary(title))


@app.route("/api/projects/<title>/auto-fetch", methods=["POST"])
def api_auto_fetch(title):
    p = project_path(title)
    if not os.path.isdir(p):
        abort(404)

    data = request.get_json(force=True) or {}
    topic = (data.get("topic") or "").strip()
    if not topic:
        return jsonify({"error": "Topic is required."}), 400

    meta = load_project_meta(title)
    category_name = data.get("category") or meta.get("category")
    category = get_category(category_name) if category_name else None
    if not category or category.get("auto_source") != "tmdb_actor":
        return jsonify({"error": "Full auto-fetch is only available for the Movie category."}), 400

    max_movies = data.get("max_items", DEFAULT_MAX_AUTO_FETCH_MOVIES)
    try:
        max_movies = int(max_movies)
    except (TypeError, ValueError):
        return jsonify({"error": "max_items must be a number."}), 400
    if max_movies < 1 or max_movies > HARD_MAX_AUTO_FETCH_MOVIES:
        return jsonify({"error": f"max_items must be between 1 and {HARD_MAX_AUTO_FETCH_MOVIES}."}), 400

    job_id = uuid.uuid4().hex[:12]
    JOBS[job_id] = {"status": "running", "progress": 0, "message": "Starting", "output_path": None}
    t = threading.Thread(
        target=run_auto_fetch_movie_job,
        args=(job_id, title, topic, max_movies),
        daemon=True,
    )
    t.start()
    return jsonify({"job_id": job_id}), 202


@app.route("/api/projects/<title>/items", methods=["POST"])
def api_fetch_items(title):
    p = project_path(title)
    if not os.path.isdir(p):
        abort(404)

    data = request.get_json(force=True) or {}
    raw_items = data.get("items") or []
    if not raw_items:
        return jsonify({"error": "No items provided."}), 400
    if len(raw_items) > MAX_ITEMS_PER_FETCH:
        return jsonify({"error": f"Too many items (max {MAX_ITEMS_PER_FETCH})."}), 400

    items = []
    for raw in raw_items:
        query = (raw.get("query") or "").strip()
        row = [str(v).strip() for v in (raw.get("row") or [])]
        if not query or not row:
            return jsonify({"error": "Each item needs a non-empty query and row."}), 400
        items.append({"query": query, "row": row})

    meta = load_project_meta(title)
    category_name = data.get("category") or meta.get("category")

    job_id = uuid.uuid4().hex[:12]
    JOBS[job_id] = {"status": "running", "progress": 0, "message": "Starting", "output_path": None}
    t = threading.Thread(
        target=run_fetch_items_job,
        args=(job_id, title, items, category_name),
        daemon=True,
    )
    t.start()
    return jsonify({"job_id": job_id}), 202


@app.route("/api/projects/<title>", methods=["GET"])
def api_get_project(title):
    if not os.path.isdir(project_path(title)):
        abort(404)
    return jsonify(project_summary(title))


@app.route("/api/projects/<title>", methods=["DELETE"])
def api_delete_project(title):
    p = project_path(title)
    if not os.path.isdir(p):
        abort(404)
    shutil.rmtree(p)
    return jsonify({"deleted": title})


@app.route("/api/projects/<title>/generate", methods=["POST"])
def api_generate(title):
    p = project_path(title)
    if not os.path.isdir(p):
        abort(404)

    summary = project_summary(title)
    if not summary["ready"]:
        return jsonify({"error": "Project is not ready.", "detail": summary}), 400

    data = request.get_json(force=True) or {}
    device = data.get("device")  # "desktop" | "mobile"

    if device == "desktop":
        res_key = data.get("resolution", "1080p")
        if res_key not in RESOLUTIONS_DESKTOP:
            return jsonify({"error": f"Unknown resolution '{res_key}'."}), 400
        width, height = RESOLUTIONS_DESKTOP[res_key]
        minutes = int(data.get("minutes", 0) or 0)
        seconds = int(data.get("seconds", 0) or 0)
        total_seconds = minutes * 60 + seconds
        if total_seconds <= 0:
            return jsonify({"error": "Enter a duration greater than 0."}), 400
    elif device == "mobile":
        width, height = RESOLUTION_MOBILE
        total_seconds = int(data.get("seconds", 30) or 30)
        if total_seconds <= 0 or total_seconds > MOBILE_MAX_SECONDS:
            return jsonify({"error": f"Mobile duration must be 1-{MOBILE_MAX_SECONDS} seconds."}), 400
    else:
        return jsonify({"error": "device must be 'desktop' or 'mobile'."}), 400

    max_items = data.get("max_items")
    if max_items is not None:
        try:
            max_items = int(max_items)
        except (TypeError, ValueError):
            return jsonify({"error": "max_items must be a number."}), 400
        if max_items < 1:
            return jsonify({"error": "max_items must be at least 1."}), 400

    job_id = uuid.uuid4().hex[:12]
    JOBS[job_id] = {"status": "running", "progress": 0, "message": "Starting", "output_path": None}
    t = threading.Thread(
        target=run_render_job,
        args=(job_id, title, device, width, height, total_seconds, max_items),
        daemon=True,
    )
    t.start()
    return jsonify({"job_id": job_id}), 202


@app.route("/api/jobs/<job_id>", methods=["GET"])
def api_job_status(job_id):
    job = JOBS.get(job_id)
    if not job:
        abort(404)
    return jsonify(job)


@app.route("/api/projects/<title>/export/<path:filename>", methods=["GET"])
def api_download_export(title, filename):
    export_dir = os.path.join(project_path(title), "Export")
    return send_from_directory(export_dir, filename, as_attachment=True)


@app.route("/api/projects/<title>/thumbnail", methods=["POST"])
def api_generate_thumbnail(title):
    p = project_path(title)
    if not os.path.isdir(p):
        abort(404)

    data = request.get_json(force=True) or {}
    device = data.get("device", "desktop")
    if device not in THUMB_SIZES:
        return jsonify({"error": "device must be 'desktop' or 'mobile'."}), 400

    images = numbered_images(os.path.join(p, "Assets"))
    if not images:
        return jsonify({"error": "No numbered images found in Assets."}), 400

    source_num = str(data.get("source", "")).strip()
    chosen_path = None
    for num, path in images:
        if str(num) == source_num:
            chosen_path = path
            break
    if chosen_path is None:
        chosen_path = images[0][1]  # default to the first image

    headline = (data.get("headline") or title).strip()

    out_name = f"thumbnail_{device}.jpg"
    out_path = os.path.join(p, "Thumbnail", out_name)

    try:
        make_thumbnail(chosen_path, headline, THUMB_SIZES[device], out_path)
    except Exception as e:
        return jsonify({"error": f"Thumbnail generation failed: {e}"}), 500

    return jsonify({"thumbnail": out_name})


@app.route("/api/projects/<title>/thumbnail/<path:filename>", methods=["GET"])
def api_get_thumbnail(title, filename):
    thumb_dir = os.path.join(project_path(title), "Thumbnail")
    return send_from_directory(thumb_dir, filename)


if __name__ == "__main__":
    app.run(debug=False, port=5050)
