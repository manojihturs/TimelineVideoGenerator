"""Render one PNG frame per ranked/interpolated data frame, honoring
every visual RaceConfig setting — orientation, color mode, labels, fonts,
grid/axis, images, background. This is the only module that touches
matplotlib; everything upstream is just data."""
import os
from concurrent.futures import ProcessPoolExecutor

import matplotlib
matplotlib.use("Agg")  # headless — no display server needed for server-side rendering

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.offsetbox import AnnotationBbox, OffsetImage
from matplotlib.patches import Ellipse
from matplotlib.lines import Line2D
from PIL import Image

from app.models.config import ColorMode, Orientation, RaceConfig, WatermarkPosition
from app.services.image_resolver import ImageResolver
from app.services.value_formatting import format_value
from app.services.style_presets import palette_for
from app.api.assets import resolve_asset_path

# fallback palette when style_preset is CUSTOM — style_presets.palette_for()
# supplies the two designed palettes (sports_light / narrative_dark). Sized
# to cover a full default bar_count (15) without wrapping, and ordered so
# consecutive entries never share a hue family (no two blues, no two
# greens back to back) — assigned in this order, adjacent bars always read
# as clearly different colors instead of subtle shade variants.
DEFAULT_PALETTE = [
    "#22C55E",  # green
    "#FACC15",  # yellow
    "#EC4899",  # pink
    "#3B82F6",  # blue
    "#F97316",  # orange
    "#8B5CF6",  # purple
    "#EF4444",  # red
    "#14B8A6",  # teal
    "#F43F5E",  # rose
    "#A3E635",  # lime
    "#6366F1",  # indigo
    "#D97706",  # amber
    "#06B6D4",  # cyan
    "#D946EF",  # fuchsia
    "#92400E",  # brown
]

# Below this many total frames, ProcessPoolExecutor's spawn overhead costs
# more than it saves — the sequential path wins for short renders/previews.
MIN_FRAMES_FOR_PARALLEL = 40


def _contrast_text_color(background_hex: str) -> tuple[str, str, str]:
    """Returns (primary_text, secondary_text, grid) colors readable
    against background_hex — perceptual luminance decides light vs. dark
    text, so a white background (like a sports-standings style chart)
    gets dark text/gridlines and a dark background gets light ones,
    without the config needing a separate text-color field for the
    common case of "just make it readable"."""
    hex_clean = background_hex.lstrip("#")
    r, g, b = (int(hex_clean[i:i + 2], 16) for i in (0, 2, 4))
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    if luminance > 0.5:
        return "#111827", "#4b5563", "#d1d5db"  # dark text/gridlines on a light background
    return "#f3f4f6", "#9ca3af", "#374151"  # light text/gridlines on a dark background


def _resolve_colors(ranked_df: pd.DataFrame, config: RaceConfig) -> dict[str, str]:
    """entity/category -> hex color, resolved once for the whole render
    so a given entity/category keeps the same color across every frame."""
    palette = palette_for(config) if config.style_preset != config.style_preset.CUSTOM else DEFAULT_PALETTE

    if config.bar_color_mode == ColorMode.SINGLE:
        keys = ranked_df["entity"].unique()
        return {k: config.single_color for k in keys}

    if config.bar_color_mode == ColorMode.CUSTOM:
        keys = ranked_df["entity"].unique()
        return {k: config.custom_color_map.get(k, palette[0]) for k in keys}

    if config.bar_color_mode == ColorMode.RANDOM:
        rng = np.random.default_rng(seed=42)  # deterministic across frames/re-renders
        keys = sorted(ranked_df["entity"].unique())
        return {k: palette[rng.integers(0, len(palette))] for k in keys}

    # CATEGORY (default): color by category, but only if it actually
    # varies — a category column that's present but constant (or blank-
    # but-non-null) across every row previously still "counted" as
    # having category data, collapsing every entity into one color
    # group. Grouping by entity instead whenever there's fewer than 2
    # distinct categories keeps bars visually distinguishable regardless
    # of how uninformative the category column turns out to be.
    group_col = "category" if ranked_df["category"].dropna().nunique() > 1 else "entity"
    keys = sorted(ranked_df[group_col].dropna().unique())
    color_by_group = {k: palette[i % len(palette)] for i, k in enumerate(keys)}
    return {
        row.entity: color_by_group.get(getattr(row, group_col), palette[0])
        for row in ranked_df.drop_duplicates("entity").itertuples(index=False)
    }


def _load_watermark(config: RaceConfig, frame_width_px: int) -> np.ndarray | None:
    """Loaded once per render job, not once per frame. Returns an RGBA
    numpy array scaled to config.watermark_scale of the frame width, or
    None if no watermark is configured (or the asset can't be read)."""
    if not config.watermark_asset_id:
        return None
    path = resolve_asset_path(config.watermark_asset_id)
    if path is None:
        return None
    try:
        img = Image.open(path).convert("RGBA")
    except Exception:
        return None
    target_w = max(1, int(frame_width_px * config.watermark_scale))
    scale = target_w / img.width
    img = img.resize((target_w, max(1, int(img.height * scale))))
    arr = np.asarray(img).astype(float)
    arr[..., 3] *= config.watermark_opacity  # apply configured opacity to the alpha channel
    return arr.astype(np.uint8)


def _watermark_anchor(position: WatermarkPosition, fig_w: int, fig_h: int, wm_w: int, wm_h: int, margin: int = 16) -> tuple[int, int]:
    if position == WatermarkPosition.TOP_LEFT:
        return margin, fig_h - margin - wm_h
    if position == WatermarkPosition.TOP_RIGHT:
        return fig_w - margin - wm_w, fig_h - margin - wm_h
    if position == WatermarkPosition.BOTTOM_LEFT:
        return margin, margin
    return fig_w - margin - wm_w, margin  # BOTTOM_RIGHT


def _period_label(frame_index: float, value_columns: list[str]) -> str:
    lo = int(np.floor(frame_index))
    hi = min(lo + 1, len(value_columns) - 1)
    if lo == hi or frame_index == lo:
        return value_columns[lo]
    frac = frame_index - lo
    return value_columns[lo] if frac < 0.5 else value_columns[hi]


def _render_state(ranked_df: pd.DataFrame, config: RaceConfig):
    """Setup that must be computed from the FULL ranked_df, not a chunk of
    it — colors depend on the complete entity/category set and max_value
    on the complete value range, so both would come out wrong (or just
    inconsistent between chunks) if a parallel worker recomputed them from
    only its own slice of frames."""
    colors = _resolve_colors(ranked_df, config)
    max_value = ranked_df["value"].max() or 1
    text_color, secondary_text_color, grid_color = _contrast_text_color(config.background_color)
    return colors, max_value, text_color, secondary_text_color, grid_color


def _create_reusable_figure(config: RaceConfig, resolution_px: tuple[int, int], watermark: np.ndarray | None):
    """Creates the Figure/Axes ONCE per render (or per worker process),
    plus the fig-level artists that never change across a job's frames
    (title, subtitle, source label, watermark image). Figure creation
    (font cache setup, backend canvas init) turned out to be a large,
    fixed per-frame cost when profiled — larger than the actual drawing —
    so reusing one Figure across every frame and just clearing+redrawing
    the Axes each time (see _render_frame_to_file's ax.cla()) is the
    single biggest lever here. Returns (fig, ax, period_label_text,
    running_total_text) — the latter two are persistent Text artists the
    per-frame draw updates via .set_text() rather than recreating (fig
    -level artists like these survive ax.cla(), so creating a fresh one
    every frame would silently accumulate overlapping duplicates)."""
    width_px, height_px = resolution_px
    dpi = 100
    fig_size = (width_px / dpi, height_px / dpi)
    text_color, secondary_text_color, _ = _contrast_text_color(config.background_color)

    fig, ax = plt.subplots(figsize=fig_size, dpi=dpi)
    fig.patch.set_facecolor(config.background_color)

    if config.title:
        fig.suptitle(config.title, color=text_color, fontsize=config.label_size_px * 1.2, fontweight="bold")
    if config.subtitle:
        # fig.text (not ax.set_title) so it survives ax.cla() between
        # frames — an axes-level title would need to be re-set every
        # frame just like the bars are
        fig.text(0.01, 0.955, config.subtitle, color=secondary_text_color,
                  fontsize=config.label_size_px * 0.7, ha="left", va="top")
    if config.data_source_label:
        fig.text(0.99, 0.01, f"Source: {config.data_source_label}", ha="right", va="bottom",
                  color=secondary_text_color, fontsize=config.label_size_px * 0.5)

    period_label_text = fig.text(0.985, 0.06, "", ha="right", va="bottom",
                                  color=text_color, fontsize=config.label_size_px * 2.2,
                                  fontweight="bold", alpha=0.85)
    running_total_text = None
    if config.show_running_total:
        running_total_text = fig.text(0.985, 0.035, "", ha="right", va="bottom",
                                       color=secondary_text_color, fontsize=config.label_size_px * 0.9)

    if watermark is not None:
        # static image, identical on every frame — set once here rather
        # than inside the per-frame draw, where calling fig.figimage()
        # again each frame would stack a new copy on top of the last
        wm_h, wm_w = watermark.shape[0], watermark.shape[1]
        x, y = _watermark_anchor(config.watermark_position, width_px, height_px, wm_w, wm_h)
        fig.figimage(watermark, xo=x, yo=y, alpha=None, zorder=10)

    return fig, ax, period_label_text, running_total_text


def _draw_clock_icon(ax, fig, frame_index: float, resolution_px: tuple[int, int], text_color: str) -> None:
    """A small clock face with sweeping hands, drawn fresh each frame just
    above the year label (bottom-right). Added via ax.add_patch/add_line
    with a figure-fraction transform so it's cleared by the next frame's
    ax.cla() along with everything else, rather than needing its own
    remove-and-recreate bookkeeping like the static watermark does.
    Rotation angle is driven directly by frame_index (not clock-accurate
    time), purely as a spinning decorative cue that the race is progressing."""
    width_px, height_px = resolution_px
    aspect = width_px / height_px  # corrects the circle/hands so they read as round, not egg-shaped, in fig-fraction coords
    cx, cy = 0.955, 0.175
    r = 0.024

    face = Ellipse((cx, cy), width=2 * r, height=2 * r * aspect, transform=fig.transFigure,
                    facecolor="white", edgecolor=text_color, linewidth=1.5, zorder=6)
    ax.add_patch(face)

    minute_angle = np.radians((frame_index * 24) % 360)
    hour_angle = np.radians((frame_index * 2) % 360)
    for angle, length, width in ((minute_angle, r * 0.78, 1.4), (hour_angle, r * 0.48, 2.2)):
        hand = Line2D(
            [cx, cx + length * np.sin(angle)],
            [cy, cy + length * aspect * np.cos(angle)],
            transform=fig.transFigure, color=text_color, linewidth=width,
            solid_capstyle="round", zorder=7,
        )
        ax.add_line(hand)


def _render_frame_to_file(
    fig,
    ax,
    period_label_text,
    running_total_text,
    frame: pd.DataFrame,
    frame_index: float,
    config: RaceConfig,
    colors: dict[str, str],
    resolver: ImageResolver | None,
    watermark: np.ndarray | None,
    max_value: float,
    resolution_px: tuple[int, int],
    text_color: str,
    secondary_text_color: str,
    grid_color: str,
    frame_path: str,
    fixed_margins: tuple[float, float, float, float] | None = None,
) -> tuple[float, float, float, float] | None:
    """Draws one frame onto the already-created fig/ax (see
    _create_reusable_figure) and saves it to frame_path. ax.cla() clears
    everything from the previous frame's bars/labels/icons; fig-level
    artists set up once (title, subtitle, source, watermark image) are
    untouched by that and don't need re-adding. If fixed_margins is
    given, applies it directly via subplots_adjust — skipping
    tight_layout()'s own internal extra full-figure draw pass, which
    profiling showed as a large share of every frame's cost (it
    re-measures every text/image artist by literally rendering the
    figure a second time). This is safe because the axis geometry
    (bar_count, rank range) is identical on every frame of a render —
    only bar lengths and text content change — so one frame's margins
    are correct for all of them. Otherwise (no fixed_margins), computes
    them via tight_layout() and returns them, for the one calibration
    call each render makes up front."""
    width_px, height_px = resolution_px
    ax.cla()
    ax.set_facecolor(config.background_color)

    labels, values, bar_colors = [], [], []
    for row in frame.itertuples(index=False):
        label = row.entity
        if config.show_category and row.category:
            label += f" ({row.category})"
        labels.append(label)
        values.append(row.value)
        bar_colors.append(colors.get(row.entity, DEFAULT_PALETTE[0]))

    # continuous, not a plain per-frame index — rank itself was eased
    # between each entity's real anchor-period ranks (dataframe_builder's
    # interpolate_frames), so a bar overtaking another glides smoothly
    # through fractional slots across the whole transition instead of
    # snapping to a new integer position the instant the interpolated
    # value crosses a neighbor's
    positions = config.bar_count - frame["rank"].to_numpy()  # rank 1 at top/right
    # room past the longest bar for the value label + entity image,
    # so neither gets clipped at the right/top edge of the frame
    value_area = max_value * 0.35 if (config.show_value or config.show_images) else max_value * 0.1

    # rank is folded into the tick label itself (not a separately
    # positioned text) — a rank number drawn near x=0 in data
    # coordinates visually collided with the tick labels matplotlib
    # already renders in that same screen region. When the name is drawn
    # on the bar itself instead (overlay_labels_on_bars), the tick is left
    # blank rather than showing it twice.
    if config.overlay_labels_on_bars:
        tick_labels = ["" for _ in labels]
    else:
        tick_labels = [f"{int(round(r))}.  {lbl}" if config.show_rank else lbl
                       for r, lbl in zip(frame["rank"], labels)]

    # extra tick-label padding when images are on, so the icon sitting
    # just inside the bar's start doesn't overlap the entity name
    # matplotlib renders just outside the axis in that same spot
    label_pad = 10 + (config.label_size_px * 1.4 if config.show_images else 0)

    if config.orientation == Orientation.HORIZONTAL:
        ax.set_xlim(0, max_value + value_area)
        ax.set_ylim(positions.min() - 0.6, positions.max() + 0.6)
        ax.set_yticks(positions)
        ax.set_yticklabels(tick_labels, color=text_color, fontsize=config.label_size_px * 0.6)
        ax.tick_params(axis="y", pad=label_pad)
        ax.xaxis.set_ticks_position("top")  # matches the sports-standings style: scale reads top-down
        ax.xaxis.set_label_position("top")
    else:
        ax.set_ylim(0, max_value + value_area)
        ax.set_xlim(positions.min() - 0.6, positions.max() + 0.6)
        ax.set_xticks(positions)
        ax.set_xticklabels(tick_labels, rotation=45, ha="right", color=text_color, fontsize=config.label_size_px * 0.6)
        ax.tick_params(axis="x", pad=label_pad)

    outside_left_transform = ax.get_yaxis_transform() if config.orientation == Orientation.HORIZONTAL else ax.get_xaxis_transform()

    for pos, value, entity, category, image_url, base_color, label in zip(
        positions, values, frame["entity"], frame["category"], frame["image_url"], bar_colors, labels,
    ):
        if value <= 0:
            continue

        # flat solid-color bar — no gradient fill/rounded end-caps. Those
        # were drawn via per-bar imshow() + Circle patches, which profiling
        # showed as the single largest per-frame cost (full-resolution
        # gradient resampling on every bar, every frame); a plain bar
        # renders in a fraction of the time with the same rank/position
        # animation and color-by-category behavior intact.
        if config.orientation == Orientation.HORIZONTAL:
            ax.barh(pos, value, height=config.bar_width_ratio, left=0, color=base_color, zorder=2)
        else:
            ax.bar(pos, value, width=config.bar_width_ratio, bottom=0, color=base_color, zorder=2)

        if config.show_value:
            # fixed points offset (not a fraction of max_value) so the
            # gap to the bar tip stays visually consistent regardless
            # of the data's scale
            text = format_value(value, config.value_format, config.value_decimal_places)
            if config.orientation == Orientation.HORIZONTAL:
                ax.annotate(text, (value, pos), xytext=(10, 0), textcoords="offset points",
                            va="center", ha="left", color=text_color, fontsize=config.label_size_px * 0.6,
                            fontweight="bold", zorder=4)
            else:
                ax.annotate(text, (pos, value), xytext=(0, 10), textcoords="offset points",
                            ha="center", va="bottom", color=text_color, fontsize=config.label_size_px * 0.6,
                            fontweight="bold", zorder=4)

        if config.overlay_labels_on_bars:
            # name in white, anchored just inside the bar's start — stays
            # readable against any bar color and tracks the bar's own
            # start point rather than the (growing) tip, Flourish-style.
            if config.orientation == Orientation.HORIZONTAL:
                ax.annotate(label, (0, pos), xytext=(12, 0), textcoords="offset points",
                            va="center", ha="left", color="white", fontsize=config.label_size_px * 0.6,
                            fontweight="bold", zorder=4)
            else:
                ax.annotate(label, (pos, 0), xytext=(0, 12), textcoords="offset points",
                            ha="center", va="bottom", color="white", fontsize=config.label_size_px * 0.6,
                            fontweight="bold", zorder=4)

        if resolver is not None:
            avatar = resolver.resolve(entity, image_url)
            # OffsetImage's zoom is a points-space scale factor, NOT a
            # data-coordinate size — deriving it from a data-space
            # bar-thickness value previously shrank the icon to a sliver
            # of a pixel. A fixed point diameter, scaled by label_size_px
            # like the rest of the chart's text, is what actually produces
            # a visible, consistently-sized icon regardless of the data's
            # value scale.
            icon_diameter_pt = config.label_size_px * 1.8
            imagebox = OffsetImage(np.asarray(avatar), zoom=icon_diameter_pt / avatar.width)

            if config.image_position == config.image_position.OUTSIDE_LEFT:
                # one logo per row, outside the plot area entirely — x is
                # in axes-fraction coords (0 = the plot's left edge) so the
                # icon sits at a fixed offset regardless of the data's
                # value scale; box_alignment=1.0 anchors the icon's own
                # right edge there, so it extends purely leftward, outside
                # the bars, never overlapping them.
                if config.orientation == Orientation.HORIZONTAL:
                    ab = AnnotationBbox(imagebox, (0, pos), xycoords=outside_left_transform,
                                         frameon=False, box_alignment=(1.15, 0.5), zorder=5)
                else:
                    ab = AnnotationBbox(imagebox, (pos, 0), xycoords=outside_left_transform,
                                         frameon=False, box_alignment=(0.5, 1.15), zorder=5)
            else:
                # inside the bar, near its start
                inset_offset = config.bar_width_ratio * 0.6
                if config.orientation == Orientation.HORIZONTAL:
                    icon_x = min(inset_offset, max(value - inset_offset, inset_offset * 0.4))
                    ab = AnnotationBbox(imagebox, (icon_x, pos), frameon=False, box_alignment=(0.5, 0.5), zorder=5)
                else:
                    icon_y = min(inset_offset, max(value - inset_offset, inset_offset * 0.4))
                    ab = AnnotationBbox(imagebox, (pos, icon_y), frameon=False, box_alignment=(0.5, 0.5), zorder=5)
            ax.add_artist(ab)

    if not config.show_axis:
        ax.set_xticks([]) if config.orientation == Orientation.HORIZONTAL else ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_visible(False)
    if config.show_grid:
        ax.grid(True, axis="x" if config.orientation == Orientation.HORIZONTAL else "y",
                color=grid_color, linewidth=0.5, alpha=0.7)
    else:
        ax.grid(False)
    for spine in ax.spines.values():
        spine.set_color(grid_color)

    ax.tick_params(colors=secondary_text_color, labelsize=config.label_size_px * 0.55)

    # title/subtitle/source label/watermark image are all set once in
    # _create_reusable_figure (they're identical on every frame of a
    # render and, being fig-level artists, survive ax.cla() above) —
    # only the period label and running total actually change per frame,
    # so those update the persistent Text artists in place rather than
    # calling fig.text() again, which would silently stack a new
    # overlapping label on top of every previous frame's.
    period_label_text.set_text(_period_label(frame_index, config.mapping.value_columns))
    if running_total_text is not None and "period_total" in frame.columns and len(frame):
        total_text = format_value(frame["period_total"].iloc[0], config.value_format, config.value_decimal_places)
        running_total_text.set_text(f"Total: {total_text}")
    if config.show_clock_icon:
        _draw_clock_icon(ax, fig, frame_index, resolution_px, text_color)

    if fixed_margins is not None:
        left, right, top, bottom = fixed_margins
        fig.subplots_adjust(left=left, right=right, top=top, bottom=bottom)
        result_margins = None
    else:
        # extra left margin to make room for logos placed outside the plot
        left_margin = 0.12 if (resolver is not None and config.image_position == config.image_position.OUTSIDE_LEFT) else 0
        fig.tight_layout(rect=(left_margin, 0.03, 1, 0.94))
        sp = fig.subplotpars
        result_margins = (sp.left, sp.right, sp.top, sp.bottom)

    # compress_level=1 (vs PIL's default 6): these PNGs are thrown away
    # the moment ffmpeg encodes them into the final video, so spending
    # CPU compressing them well is pure waste.
    fig.savefig(frame_path, facecolor=config.background_color,
                transparent=config.transparent_background,
                pil_kwargs={"compress_level": 1})
    return result_margins


def _calibrate_margins(
    ranked_df: pd.DataFrame,
    config: RaceConfig,
    colors: dict[str, str],
    resolver: ImageResolver | None,
    watermark: np.ndarray | None,
    max_value: float,
    resolution_px: tuple[int, int],
    text_color: str,
    secondary_text_color: str,
    grid_color: str,
    output_dir: str,
) -> tuple[float, float, float, float]:
    """One real tight_layout() pass, on a representative middle frame, to
    get the fixed margins every other frame in the render will reuse. The
    frame is written then discarded — it isn't one of the numbered output
    frames, so it can't disturb ffmpeg's contiguous frame_%05d.png
    sequence."""
    frame_indices = sorted(ranked_df["frame_index"].unique())
    calib_index = frame_indices[len(frame_indices) // 2]
    calib_frame = ranked_df[ranked_df.frame_index == calib_index].sort_values("rank")
    calib_path = os.path.join(output_dir, "_margin_calibration.png")
    fig, ax, period_label_text, running_total_text = _create_reusable_figure(config, resolution_px, watermark)
    try:
        margins = _render_frame_to_file(fig, ax, period_label_text, running_total_text,
                                         calib_frame, calib_index, config, colors, resolver, watermark, max_value,
                                         resolution_px, text_color, secondary_text_color, grid_color, calib_path)
    finally:
        plt.close(fig)
    try:
        os.remove(calib_path)
    except OSError:
        pass
    return margins


def render_frames(
    ranked_df: pd.DataFrame,
    config: RaceConfig,
    output_dir: str,
    resolution_px: tuple[int, int],
) -> list[str]:
    """One PNG per unique frame_index in ranked_df, rendered sequentially
    in this process. Returns the ordered list of frame file paths
    (out_dir/frame_00000.png, ...)."""
    os.makedirs(output_dir, exist_ok=True)
    if ranked_df.empty:
        return []

    colors, max_value, text_color, secondary_text_color, grid_color = _render_state(ranked_df, config)
    resolver = ImageResolver(size=64) if config.show_images else None
    watermark = _load_watermark(config, resolution_px[0])
    margins = _calibrate_margins(ranked_df, config, colors, resolver, watermark, max_value,
                                  resolution_px, text_color, secondary_text_color, grid_color, output_dir)

    frame_indices = sorted(ranked_df["frame_index"].unique())
    paths = []
    fig, ax, period_label_text, running_total_text = _create_reusable_figure(config, resolution_px, watermark)
    try:
        for i, frame_index in enumerate(frame_indices):
            frame = ranked_df[ranked_df.frame_index == frame_index].sort_values("rank")
            frame_path = os.path.join(output_dir, f"frame_{i:05d}.png")
            _render_frame_to_file(fig, ax, period_label_text, running_total_text,
                                   frame, frame_index, config, colors, resolver, watermark, max_value,
                                   resolution_px, text_color, secondary_text_color, grid_color, frame_path,
                                   fixed_margins=margins)
            paths.append(frame_path)
    finally:
        plt.close(fig)

    return paths


def _render_chunk_worker(args) -> list[str]:
    """Runs in its own process. Rebuilds the image resolver/watermark
    locally (cheap and deterministic, so it's simpler than pickling them
    across the process boundary) and writes this chunk's frames using
    globally-correct, gap-free filenames via start_index — required so
    ffmpeg's frame_%05d.png pattern stays contiguous across all workers'
    output. Margins are precomputed once in the parent process and passed
    in, so no worker needs its own tight_layout() calibration pass."""
    (chunk_df, config, colors, max_value, text_color, secondary_text_color,
     grid_color, resolution_px, output_dir, start_index, margins) = args

    resolver = ImageResolver(size=64) if config.show_images else None
    watermark = _load_watermark(config, resolution_px[0])

    frame_indices = sorted(chunk_df["frame_index"].unique())
    paths = []
    fig, ax, period_label_text, running_total_text = _create_reusable_figure(config, resolution_px, watermark)
    try:
        for offset, frame_index in enumerate(frame_indices):
            frame = chunk_df[chunk_df.frame_index == frame_index].sort_values("rank")
            frame_path = os.path.join(output_dir, f"frame_{start_index + offset:05d}.png")
            _render_frame_to_file(fig, ax, period_label_text, running_total_text,
                                   frame, frame_index, config, colors, resolver, watermark, max_value,
                                   resolution_px, text_color, secondary_text_color, grid_color, frame_path,
                                   fixed_margins=margins)
            paths.append(frame_path)
    finally:
        plt.close(fig)
    return paths


def render_frames_parallel(
    ranked_df: pd.DataFrame,
    config: RaceConfig,
    output_dir: str,
    resolution_px: tuple[int, int],
    max_workers: int | None = None,
) -> list[str]:
    """Same output as render_frames, but splits frames across worker
    processes — each frame is fully independent given the already-computed
    ranked_df, so this is a pure wall-clock win on multi-core machines.
    Falls back to the sequential path below MIN_FRAMES_FOR_PARALLEL, where
    process-spawn overhead would cost more than it saves."""
    os.makedirs(output_dir, exist_ok=True)
    if ranked_df.empty:
        return []

    frame_indices = sorted(ranked_df["frame_index"].unique())
    workers = max_workers or os.cpu_count() or 1
    if len(frame_indices) < MIN_FRAMES_FOR_PARALLEL or workers <= 1:
        return render_frames(ranked_df, config, output_dir, resolution_px)

    colors, max_value, text_color, secondary_text_color, grid_color = _render_state(ranked_df, config)
    resolver = ImageResolver(size=64) if config.show_images else None
    watermark = _load_watermark(config, resolution_px[0])
    margins = _calibrate_margins(ranked_df, config, colors, resolver, watermark, max_value,
                                  resolution_px, text_color, secondary_text_color, grid_color, output_dir)

    n_workers = min(workers, len(frame_indices))
    chunks = np.array_split(np.array(frame_indices), n_workers)

    tasks = []
    start_index = 0
    for chunk in chunks:
        if len(chunk) == 0:
            continue
        chunk_df = ranked_df[ranked_df["frame_index"].isin(chunk)]
        tasks.append((chunk_df, config, colors, max_value, text_color, secondary_text_color,
                      grid_color, resolution_px, output_dir, start_index, margins))
        start_index += len(chunk)

    all_paths = []
    with ProcessPoolExecutor(max_workers=len(tasks)) as executor:
        for result in executor.map(_render_chunk_worker, tasks):
            all_paths.extend(result)

    all_paths.sort()
    return all_paths
