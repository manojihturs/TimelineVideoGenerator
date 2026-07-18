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
  jobs (in-memory dict)  -> background render jobs, polled by the UI

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
import os
import re
import shutil
import subprocess
import threading
import time
import uuid

from flask import Flask, jsonify, request, send_from_directory, abort
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECTS_DIR = os.path.join(BASE_DIR, "projects")
os.makedirs(PROJECTS_DIR, exist_ok=True)

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
    return {
        "title": title,
        "folders_ok": folders_ok,
        "asset_count": len(images),
        "asset_numbers": [num for num, _ in images],
        "assets_ok": len(images) > 0,
        "csv_ok": not csv_is_empty(data_csv),
        "narration_count": len(narr),
        "narration_ok": len(narr) > 0,
        "ready": folders_ok and len(images) > 0 and not csv_is_empty(data_csv),
        "exports": sorted(os.listdir(os.path.join(p, "Export")))
        if os.path.isdir(os.path.join(p, "Export"))
        else [],
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


def build_recap_frame(image_path, columns, width, height, card_index):
    """Compose one 'recap card': source image cropped to best-fill a bold
    color panel up top, stacked colored bands below it — one per CSV
    column — each with bold, white-stroked, auto-fit text. Verdict-style
    words (FLOP/HIT/BLOCKBUSTER/...) get their own accent color. Returns
    a PIL Image (card_index only affects the poster panel's color, so
    consecutive cards in a scroll don't look identical)."""
    poster_bg = POSTER_BG_PALETTE[card_index % len(POSTER_BG_PALETTE)]
    canvas = Image.new("RGB", (width, height), "#000000")

    poster_zone_h = int(height * 0.52)
    add_poster_texture(canvas, 0, 0, width, poster_zone_h, poster_bg)

    src = Image.open(image_path).convert("RGB")
    fitted = cover_fit(src, width, poster_zone_h)  # best-fit: fill, no empty margin
    canvas.paste(fitted, (0, 0))

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


def build_scroll_strip(objects, width, height, gap):
    """Lay out every card left-to-right with a fixed gap between them —
    non-overlapping by construction — into one wide image ready to be
    panned across."""
    n = len(objects)
    strip_w = n * width + (n - 1) * gap
    strip = Image.new("RGB", (strip_w, height), "#0E1014")  # gap color

    x = 0
    for card_index, (num, img_path, columns) in enumerate(objects):
        card = build_recap_frame(img_path, columns, width, height, card_index)
        strip.paste(card, (x, 0))
        x += width + gap

    return strip, strip_w


def render_scroll_video(strip_path, width, height, total_seconds, out_path):
    """Pan a constant-speed crop window right-to-left across the strip —
    the scroll IS the transition, so cards are revealed one after another
    with no cuts. eval=frame makes ffmpeg recompute x every frame instead
    of once at init."""
    strip_w = Image.open(strip_path).size[0]
    travel = max(1, strip_w - width)
    speed = travel / total_seconds  # px/sec

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", strip_path,
        "-filter_complex", f"[0:v]crop=w={width}:h={height}:x=t*{speed:.5f}:y=0[out]",
        "-map", "[out]",
        "-t", str(total_seconds),
        "-r", "30",
        "-pix_fmt", "yuv420p",
        "-c:v", "libx264",
        out_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def build_narration_track(audio_paths, out_path):
    """Concatenate one or more Narration/ audio files (any mix of formats)
    into a single track using filter_complex, which tolerates mismatched
    codecs/sample rates better than the concat demuxer."""
    if len(audio_paths) == 1:
        cmd = ["ffmpeg", "-y", "-i", audio_paths[0], "-c:a", "aac", out_path]
        subprocess.run(cmd, check=True, capture_output=True)
        return

    inputs = []
    for a in audio_paths:
        inputs += ["-i", a]
    n = len(audio_paths)
    filter_str = "".join(f"[{i}:a]" for i in range(n)) + f"concat=n={n}:v=0:a=1[aout]"
    cmd = ["ffmpeg", "-y", *inputs, "-filter_complex", filter_str, "-map", "[aout]", "-c:a", "aac", out_path]
    subprocess.run(cmd, check=True, capture_output=True)


def mux_narration(silent_video_path, narration_path, total_seconds, out_path):
    """Attach narration as the audio track, looping it if shorter than the
    video and trimming if longer, so the final file always runs exactly
    total_seconds."""
    cmd = [
        "ffmpeg", "-y",
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


def run_render_job(job_id, title, device, width, height, total_seconds):
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

        if not objects:
            raise RuntimeError(
                "No CSV rows matched a numbered image. Make sure row 1 has a "
                "1.jpg, row 2 has a 2.jpg, etc."
            )

        tmp_dir = os.path.join(export_dir, f"_tmp_{job_id}")
        os.makedirs(tmp_dir, exist_ok=True)

        job["progress"] = 10
        job["message"] = f"Building {len(objects)} card(s)"
        gap = max(12, int(width * 0.035))
        strip, strip_w = build_scroll_strip(objects, width, height, gap)
        strip_path = os.path.join(tmp_dir, "strip.png")
        strip.save(strip_path)

        job["progress"] = 55
        job["message"] = "Rendering scroll"
        out_name = f"{title}_{device}.mp4"
        out_path = os.path.join(export_dir, out_name)

        narr = narration_files(p)
        if narr:
            silent_path = os.path.join(tmp_dir, "silent.mp4")
            render_scroll_video(strip_path, width, height, total_seconds, silent_path)

            job["progress"] = 90
            job["message"] = "Mixing narration"
            narration_track = os.path.join(tmp_dir, "narration.m4a")
            build_narration_track(narr, narration_track)
            mux_narration(silent_path, narration_track, total_seconds, out_path)
        else:
            render_scroll_video(strip_path, width, height, total_seconds, out_path)

        shutil.rmtree(tmp_dir, ignore_errors=True)

        job["status"] = "done"
        job["progress"] = 100
        job["message"] = "Export complete"
        job["output_path"] = out_name
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

    job_id = uuid.uuid4().hex[:12]
    JOBS[job_id] = {"status": "running", "progress": 0, "message": "Starting", "output_path": None}
    t = threading.Thread(
        target=run_render_job,
        args=(job_id, title, device, width, height, total_seconds),
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
