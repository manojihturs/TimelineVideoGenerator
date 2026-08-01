"""Second render engine (RenderEngine.CANVAS): plays the chart live in a
headless Chromium tab (HTML5 Canvas + a JS animation loop) and captures
that playback as video via Playwright's built-in recorder — the same
technique Flourish uses (browser rendering + capture), instead of
matplotlib's one-PNG-per-frame + ffmpeg-encode pipeline in race_renderer.py.
Capture wall-clock time is bounded by the video's own duration, not by
frame count x per-frame render cost, which is why this is dramatically
faster on long/high-frame-count renders.

All text (period labels, formatted values, running totals) and all colors
are computed server-side, identically to race_renderer.py, and simply
handed to the page as data — the goal is the same visual design as the
matplotlib engine, not a different one, just produced faster."""
import base64
import glob
import json
import mimetypes
import os

import pandas as pd
from playwright.sync_api import sync_playwright

from app.api.assets import resolve_asset_path
from app.models.config import Orientation, RaceConfig, WatermarkPosition
from app.services.race_renderer import _contrast_text_color, _period_label, _resolve_colors
from app.services.value_formatting import format_value

# Capture wall-clock time is NOT the video's own duration — drawing +
# video-encoding overhead per tick measured at roughly 1.4x the content
# duration in testing, plus a fixed browser-launch cost. This must scale
# with duration (a flat buffer was measured to time out on a real 5-minute
# render that was still progressing normally, just slower than content time).
CAPTURE_WALLCLOCK_MULTIPLIER = 2.2  # generous margin over the measured ~1.4x ratio
CAPTURE_TIMEOUT_FIXED_MS = 30_000


def _watermark_data_uri(config: RaceConfig) -> str | None:
    if not config.watermark_asset_id:
        return None
    path = resolve_asset_path(config.watermark_asset_id)
    if path is None:
        return None
    try:
        mime = mimetypes.guess_type(str(path))[0] or "image/png"
        with open(path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode("ascii")
        return f"data:{mime};base64,{encoded}"
    except OSError:
        return None


def _build_frame_payload(ranked_df: pd.DataFrame, config: RaceConfig, colors: dict[str, str]) -> list[dict]:
    frame_indices = sorted(ranked_df["frame_index"].unique())
    value_columns = config.mapping.value_columns
    frames = []
    for frame_index in frame_indices:
        frame = ranked_df[ranked_df["frame_index"] == frame_index].sort_values("rank")
        bars = []
        for row in frame.itertuples(index=False):
            if row.value <= 0:
                continue
            label = row.entity
            if config.show_category and row.category:
                label += f" ({row.category})"
            bars.append({
                "entity": row.entity,
                "label": label,
                "value": float(row.value),
                "rank": float(row.rank),
                "color": colors.get(row.entity, "#2563EB"),
                "imageUrl": row.image_url if isinstance(row.image_url, str) and row.image_url else None,
                "valueText": format_value(row.value, config.value_format, config.value_decimal_places) if config.show_value else None,
            })
        entry = {"periodLabel": _period_label(frame_index, value_columns), "bars": bars}
        if config.show_running_total and "period_total" in frame.columns and len(frame):
            entry["totalText"] = format_value(frame["period_total"].iloc[0], config.value_format, config.value_decimal_places)
        frames.append(entry)
    return frames


def _build_html(
    frames: list[dict],
    config: RaceConfig,
    resolution_px: tuple[int, int],
    max_value: float,
    text_color: str,
    secondary_text_color: str,
    grid_color: str,
    watermark_data_uri: str | None,
) -> str:
    width_px, height_px = resolution_px
    payload = {
        "frames": frames,
        "width": width_px,
        "height": height_px,
        "fps": config.fps,
        "barCount": config.bar_count,
        "orientation": config.orientation.value,
        "backgroundColor": config.background_color,
        "textColor": text_color,
        "secondaryTextColor": secondary_text_color,
        "gridColor": grid_color,
        "labelSizePx": config.label_size_px,
        "title": config.title,
        "subtitle": config.subtitle,
        "sourceLabel": f"Source: {config.data_source_label}" if config.data_source_label else "",
        "showImages": config.show_images,
        "imagePosition": config.image_position.value,
        "overlayLabelsOnBars": config.overlay_labels_on_bars,
        "showRank": config.show_rank,
        "showAxis": config.show_axis,
        "showGrid": config.show_grid,
        "showClockIcon": config.show_clock_icon,
        "maxValue": max_value,
        "watermark": watermark_data_uri,
        "watermarkPosition": config.watermark_position.value,
        "watermarkOpacity": config.watermark_opacity,
        "watermarkScale": config.watermark_scale,
    }
    # JSON going into an inline <script> block — guard the one sequence
    # that would otherwise prematurely close it if a title/label ever
    # contained "</script>" verbatim.
    payload_json = json.dumps(payload).replace("</", "<\\/")

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><style>
html,body{{margin:0;padding:0;overflow:hidden;}}
canvas{{display:block;}}
</style></head>
<body>
<canvas id="c" width="{width_px}" height="{height_px}"></canvas>
<script>
const DATA = {payload_json};
const ctx = document.getElementById('c').getContext('2d');
const W = DATA.width, H = DATA.height;
const HORIZONTAL = DATA.orientation === 'horizontal';

const imageCache = new Map();  // url -> {{img, loaded, failed}}
function getImage(url) {{
  if (!url) return null;
  let entry = imageCache.get(url);
  if (!entry) {{
    entry = {{img: new Image(), loaded: false, failed: false}};
    entry.img.crossOrigin = 'anonymous';
    entry.img.onload = () => {{ entry.loaded = true; }};
    entry.img.onerror = () => {{ entry.failed = true; }};
    entry.img.src = url;
    imageCache.set(url, entry);
  }}
  return entry;
}}

// deterministic string hash -> fallback avatar color, mirroring the
// server-side initials-avatar palette used when an entity has no image
// or the fetch fails (image_resolver.py's AVATAR_PALETTE)
const AVATAR_PALETTE = ["#7C3AED","#2563EB","#059669","#D97706","#DC2626","#DB2777","#0891B2","#65A30D","#9333EA","#EA580C"];
function colorForFallback(key) {{
  let h = 0;
  for (let i = 0; i < key.length; i++) h = (h * 31 + key.charCodeAt(i)) >>> 0;
  return AVATAR_PALETTE[h % AVATAR_PALETTE.length];
}}
function initials(name) {{
  return name.split(' ').slice(0, 2).map(w => w[0] ? w[0].toUpperCase() : '').join('') || '?';
}}

function drawAvatar(cx, cy, radius, entity, url) {{
  const entry = getImage(url);
  ctx.save();
  ctx.beginPath();
  ctx.arc(cx, cy, radius, 0, Math.PI * 2);
  ctx.closePath();
  if (entry && entry.loaded && !entry.failed) {{
    ctx.clip();
    const img = entry.img;
    const scale = (radius * 2) / Math.min(img.width, img.height);
    const dw = img.width * scale, dh = img.height * scale;
    ctx.drawImage(img, cx - dw / 2, cy - dh / 2, dw, dh);
  }} else {{
    ctx.fillStyle = colorForFallback(entity);
    ctx.fill();
    ctx.fillStyle = '#ffffff';
    ctx.font = `bold ${{Math.round(radius)}}px ${{'Arial, sans-serif'}}`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(initials(entity), cx, cy + 1);
  }}
  ctx.restore();
}}

let watermarkImg = null;
if (DATA.watermark) {{
  watermarkImg = new Image();
  watermarkImg.src = DATA.watermark;
}}
function drawWatermark() {{
  if (!watermarkImg || !watermarkImg.complete || !watermarkImg.naturalWidth) return;
  const targetW = W * DATA.watermarkScale;
  const scale = targetW / watermarkImg.naturalWidth;
  const w = targetW, h = watermarkImg.naturalHeight * scale;
  const margin = 16;
  let x, y;
  if (DATA.watermarkPosition === 'top_left') {{ x = margin; y = margin; }}
  else if (DATA.watermarkPosition === 'top_right') {{ x = W - margin - w; y = margin; }}
  else if (DATA.watermarkPosition === 'bottom_left') {{ x = margin; y = H - margin - h; }}
  else {{ x = W - margin - w; y = H - margin - h; }}
  ctx.save();
  ctx.globalAlpha = DATA.watermarkOpacity;
  ctx.drawImage(watermarkImg, x, y, w, h);
  ctx.restore();
}}

function drawClock(frameIndex) {{
  const cx = W * 0.955, cy = H * 0.83;
  const r = Math.min(W, H) * 0.024;
  ctx.save();
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, Math.PI * 2);
  ctx.fillStyle = '#ffffff';
  ctx.fill();
  ctx.lineWidth = 1.5;
  ctx.strokeStyle = DATA.textColor;
  ctx.stroke();

  const minuteAngle = (frameIndex * 24 % 360) * Math.PI / 180;
  const hourAngle = (frameIndex * 2 % 360) * Math.PI / 180;
  ctx.strokeStyle = DATA.textColor;
  ctx.lineCap = 'round';

  ctx.lineWidth = 1.4;
  ctx.beginPath();
  ctx.moveTo(cx, cy);
  ctx.lineTo(cx + r * 0.78 * Math.sin(minuteAngle), cy - r * 0.78 * Math.cos(minuteAngle));
  ctx.stroke();

  ctx.lineWidth = 2.2;
  ctx.beginPath();
  ctx.moveTo(cx, cy);
  ctx.lineTo(cx + r * 0.48 * Math.sin(hourAngle), cy - r * 0.48 * Math.cos(hourAngle));
  ctx.stroke();
  ctx.restore();
}}

// layout, mirrored from race_renderer.py's fixed-margin approach: fixed
// fractions of the canvas rather than measuring text, since canvas has
// no tight_layout() equivalent — good enough for a consistent design,
// not meant to be pixel-identical to matplotlib's own metrics.
const PLOT = {{
  top: H * (DATA.title ? 0.13 : 0.06),
  bottom: H * 0.06,
  left: W * (DATA.showImages && DATA.imagePosition === 'outside_left' ? 0.14 : 0.03),
  right: W * 0.14,
}};
const plotW = W - PLOT.left - PLOT.right;
const plotH = H - PLOT.top - PLOT.bottom;
const rowSpan = HORIZONTAL ? plotH / DATA.barCount : plotW / DATA.barCount;

function formatAxisValue(v) {{
  if (v >= 1e9) return (v / 1e9).toFixed(1) + 'B';
  if (v >= 1e6) return (v / 1e6).toFixed(1) + 'M';
  if (v >= 1e3) return (v / 1e3).toFixed(0) + 'K';
  return String(Math.round(v));
}}

function drawAxis() {{
  if (!DATA.showAxis) return;
  const ticks = 6;
  ctx.font = `${{Math.round(DATA.labelSizePx * 0.55)}}px Arial, sans-serif`;
  ctx.fillStyle = DATA.secondaryTextColor;
  ctx.strokeStyle = DATA.gridColor;
  ctx.lineWidth = 1;
  for (let i = 0; i <= ticks; i++) {{
    const frac = i / ticks;
    if (HORIZONTAL) {{
      const x = PLOT.left + frac * plotW;
      ctx.textAlign = 'center';
      ctx.fillText(formatAxisValue(DATA.maxValue * frac), x, PLOT.top - 12);
      if (DATA.showGrid) {{
        ctx.beginPath();
        ctx.moveTo(x, PLOT.top);
        ctx.lineTo(x, PLOT.top + plotH);
        ctx.stroke();
      }}
    }} else {{
      const y = PLOT.top + plotH - frac * plotH;
      ctx.textAlign = 'right';
      ctx.fillText(formatAxisValue(DATA.maxValue * frac), PLOT.left - 8, y + 4);
      if (DATA.showGrid) {{
        ctx.beginPath();
        ctx.moveTo(PLOT.left, y);
        ctx.lineTo(PLOT.left + plotW, y);
        ctx.stroke();
      }}
    }}
  }}
}}

function draw(frame, frameIndex) {{
  ctx.fillStyle = DATA.backgroundColor;
  ctx.fillRect(0, 0, W, H);

  if (DATA.title) {{
    ctx.fillStyle = DATA.textColor;
    ctx.font = `bold ${{Math.round(DATA.labelSizePx * 1.6)}}px Arial, sans-serif`;
    ctx.textAlign = 'center';
    ctx.fillText(DATA.title, W / 2, H * 0.06);
  }}
  if (DATA.subtitle) {{
    ctx.fillStyle = DATA.secondaryTextColor;
    ctx.font = `${{Math.round(DATA.labelSizePx * 0.9)}}px Arial, sans-serif`;
    ctx.textAlign = 'left';
    ctx.fillText(DATA.subtitle, W * 0.02, H * 0.045);
  }}

  drawAxis();

  const barThickness = rowSpan * 0.78;
  for (const bar of frame.bars) {{
    const slot = PLOT_ORIGIN_FOR(bar.rank);
    const lengthFrac = bar.value / DATA.maxValue;

    ctx.fillStyle = bar.color;
    if (HORIZONTAL) {{
      const barW = lengthFrac * plotW;
      ctx.fillRect(PLOT.left, slot - barThickness / 2, barW, barThickness);

      let afterBarX = PLOT.left + barW + 10;
      if (DATA.overlayLabelsOnBars) {{
        // white text reads fine while it fits inside the bar's own color,
        // but a short bar (a low-share entity, or an early frame before
        // the bar has grown) can't fit the label — white text spilling
        // past the bar tip onto the white page background goes invisible.
        // Falling back to solid text just past the bar tip, like the
        // non-overlay label style, keeps every row's label always readable.
        ctx.font = `bold ${{Math.round(DATA.labelSizePx)}}px Arial, sans-serif`;
        const labelWidth = ctx.measureText(bar.label).width;
        const fitsInsideBar = labelWidth + 24 <= barW;
        ctx.textAlign = 'left';
        ctx.textBaseline = 'middle';
        if (fitsInsideBar) {{
          ctx.fillStyle = '#ffffff';
          ctx.fillText(bar.label, PLOT.left + 12, slot);
        }} else {{
          ctx.fillStyle = DATA.textColor;
          ctx.fillText(bar.label, afterBarX, slot);
          afterBarX += labelWidth + 10;
        }}
      }} else {{
        ctx.fillStyle = DATA.textColor;
        ctx.font = `${{Math.round(DATA.labelSizePx * 0.8)}}px Arial, sans-serif`;
        ctx.textAlign = 'right';
        ctx.textBaseline = 'middle';
        const rankPrefix = DATA.showRank ? `${{Math.round(bar.rank)}}.  ` : '';
        ctx.fillText(rankPrefix + bar.label, PLOT.left - 14, slot);
      }}

      if (bar.valueText) {{
        ctx.fillStyle = DATA.textColor;
        ctx.font = `bold ${{Math.round(DATA.labelSizePx * 0.8)}}px Arial, sans-serif`;
        ctx.textAlign = 'left';
        ctx.textBaseline = 'middle';
        ctx.fillText(bar.valueText, afterBarX, slot);
      }}

      if (DATA.showImages) {{
        const radius = rowSpan * 0.32;
        if (DATA.imagePosition === 'outside_left') {{
          drawAvatar(PLOT.left - radius - 18, slot, radius, bar.entity, bar.imageUrl);
        }} else {{
          const iconX = Math.min(PLOT.left + barW - radius * 1.2, PLOT.left + radius * 1.2);
          drawAvatar(Math.max(iconX, PLOT.left + radius * 1.2), slot, radius, bar.entity, bar.imageUrl);
        }}
      }}
    }} else {{
      const barH = lengthFrac * plotH;
      const barY = PLOT.top + plotH - barH;
      ctx.fillRect(slot - barThickness / 2, barY, barThickness, barH);

      if (DATA.overlayLabelsOnBars) {{
        ctx.save();
        ctx.fillStyle = '#ffffff';
        ctx.font = `bold ${{Math.round(DATA.labelSizePx)}}px Arial, sans-serif`;
        ctx.textAlign = 'left';
        ctx.textBaseline = 'middle';
        ctx.translate(slot, PLOT.top + plotH - 12);
        ctx.rotate(-Math.PI / 2);
        ctx.fillText(bar.label, 0, 0);
        ctx.restore();
      }} else {{
        ctx.save();
        ctx.fillStyle = DATA.textColor;
        ctx.font = `${{Math.round(DATA.labelSizePx * 0.75)}}px Arial, sans-serif`;
        ctx.textAlign = 'right';
        ctx.textBaseline = 'middle';
        ctx.translate(slot, PLOT.top + plotH + 14);
        ctx.rotate(-Math.PI / 4);
        const rankPrefix = DATA.showRank ? `${{Math.round(bar.rank)}}.  ` : '';
        ctx.fillText(rankPrefix + bar.label, 0, 0);
        ctx.restore();
      }}

      if (bar.valueText) {{
        ctx.fillStyle = DATA.textColor;
        ctx.font = `bold ${{Math.round(DATA.labelSizePx * 0.8)}}px Arial, sans-serif`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'bottom';
        ctx.fillText(bar.valueText, slot, barY - 6);
      }}

      if (DATA.showImages) {{
        const radius = rowSpan * 0.32;
        drawAvatar(slot, barY - radius - 12, radius, bar.entity, bar.imageUrl);
      }}
    }}
  }}

  drawWatermark();

  ctx.fillStyle = DATA.textColor;
  ctx.font = `bold ${{Math.round(DATA.labelSizePx * 2)}}px Arial, sans-serif`;
  ctx.textAlign = 'right';
  ctx.textBaseline = 'alphabetic';
  ctx.fillText(frame.periodLabel, W * 0.985, H * 0.95);

  if (frame.totalText) {{
    ctx.fillStyle = DATA.secondaryTextColor;
    ctx.font = `${{Math.round(DATA.labelSizePx * 0.85)}}px Arial, sans-serif`;
    ctx.fillText('Total: ' + frame.totalText, W * 0.985, H * 0.97);
  }}

  if (DATA.showClockIcon) drawClock(frameIndex);

  if (DATA.sourceLabel) {{
    ctx.fillStyle = DATA.secondaryTextColor;
    ctx.font = `${{Math.round(DATA.labelSizePx * 0.5)}}px Arial, sans-serif`;
    ctx.textAlign = 'right';
    ctx.fillText(DATA.sourceLabel, W * 0.99, H * 0.99);
  }}
}}

function PLOT_ORIGIN_FOR(rank) {{
  const idx = rank - 1;
  return HORIZONTAL ? (PLOT.top + idx * rowSpan + rowSpan / 2)
                     : (PLOT.left + idx * rowSpan + rowSpan / 2);
}}

let i = 0;
window.__DONE__ = false;
function tick() {{
  if (i >= DATA.frames.length) {{ window.__DONE__ = true; return; }}
  draw(DATA.frames[i], i);
  i++;
  setTimeout(tick, 1000 / DATA.fps);
}}
tick();
</script>
</body></html>
"""


def render_canvas_video(
    ranked_df: pd.DataFrame,
    config: RaceConfig,
    output_dir: str,
    resolution_px: tuple[int, int],
) -> str:
    """Renders the full animation by playing it live in headless Chromium
    and capturing the playback as a .webm — returns the path to that raw
    captured video (still needs transcoding to the requested export
    format; see video_encoder.transcode_captured_video)."""
    os.makedirs(output_dir, exist_ok=True)
    if ranked_df.empty:
        raise ValueError("No frames to render")

    colors = _resolve_colors(ranked_df, config)
    max_value = ranked_df["value"].max() or 1
    text_color, secondary_text_color, grid_color = _contrast_text_color(config.background_color)

    frames = _build_frame_payload(ranked_df, config, colors)
    watermark_data_uri = _watermark_data_uri(config)
    html = _build_html(frames, config, resolution_px, max_value,
                        text_color, secondary_text_color, grid_color, watermark_data_uri)

    html_path = os.path.join(output_dir, "_canvas_race.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    duration_ms = len(frames) / config.fps * 1000
    timeout_ms = duration_ms * CAPTURE_WALLCLOCK_MULTIPLIER + CAPTURE_TIMEOUT_FIXED_MS

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(
            viewport={"width": resolution_px[0], "height": resolution_px[1]},
            record_video_dir=output_dir,
            record_video_size={"width": resolution_px[0], "height": resolution_px[1]},
        )
        page = context.new_page()
        page.goto(f"file:///{html_path.replace(os.sep, '/')}")
        page.wait_for_function("window.__DONE__ === true", timeout=timeout_ms)
        context.close()
        browser.close()

    webm_files = glob.glob(os.path.join(output_dir, "*.webm"))
    if not webm_files:
        raise RuntimeError("Canvas capture produced no video output")
    return webm_files[0]
