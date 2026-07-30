"""Render one PNG frame per ranked/interpolated data frame, honoring
every visual RaceConfig setting — orientation, color mode, labels, fonts,
grid/axis, images, background. This is the only module that touches
matplotlib; everything upstream is just data."""
import os

import matplotlib
matplotlib.use("Agg")  # headless — no display server needed for server-side rendering

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.offsetbox import AnnotationBbox, OffsetImage
from PIL import Image

from app.models.config import ColorMode, Orientation, RaceConfig, WatermarkPosition
from app.services.image_resolver import ImageResolver
from app.services.value_formatting import format_value
from app.services.style_presets import palette_for
from app.api.assets import resolve_asset_path

# fallback palette when style_preset is CUSTOM — style_presets.palette_for()
# supplies the two designed palettes (sports_light / narrative_dark)
DEFAULT_PALETTE = [
    "#2563EB", "#DC2626", "#059669", "#D97706", "#7C3AED",
    "#0891B2", "#DB2777", "#65A30D", "#EA580C", "#4F46E5",
]


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

    # CATEGORY (default): color by category if present, else fall back to entity
    group_col = "category" if ranked_df["category"].notna().any() else "entity"
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


def render_frames(
    ranked_df: pd.DataFrame,
    config: RaceConfig,
    output_dir: str,
    resolution_px: tuple[int, int],
) -> list[str]:
    """One PNG per unique frame_index in ranked_df. Returns the ordered
    list of frame file paths (out_dir/frame_00000.png, ...)."""
    os.makedirs(output_dir, exist_ok=True)
    if ranked_df.empty:
        return []

    width_px, height_px = resolution_px
    dpi = 100
    fig_size = (width_px / dpi, height_px / dpi)
    colors = _resolve_colors(ranked_df, config)
    resolver = ImageResolver(size=64) if config.show_images else None
    max_value = ranked_df["value"].max() or 1
    watermark = _load_watermark(config, width_px)

    frame_indices = sorted(ranked_df["frame_index"].unique())
    paths = []

    text_color, secondary_text_color, grid_color = _contrast_text_color(config.background_color)

    for i, frame_index in enumerate(frame_indices):
        frame = ranked_df[ranked_df.frame_index == frame_index].sort_values("rank")

        fig, ax = plt.subplots(figsize=fig_size, dpi=dpi)
        fig.patch.set_facecolor(config.background_color)
        ax.set_facecolor(config.background_color)

        labels, values, bar_colors = [], [], []
        for row in frame.itertuples(index=False):
            label = row.entity
            if config.show_category and row.category:
                label += f" ({row.category})"
            labels.append(label)
            values.append(row.value)
            bar_colors.append(colors.get(row.entity, DEFAULT_PALETTE[0]))

        positions = np.arange(len(frame))[::-1]  # rank 1 at top/right
        # room past the longest bar for the value label + entity image,
        # so neither gets clipped at the right/top edge of the frame
        value_area = max_value * 0.35 if (config.show_value or config.show_images) else max_value * 0.1

        # rank is folded into the tick label itself (not a separately
        # positioned text) — a rank number drawn near x=0 in data
        # coordinates visually collided with the tick labels matplotlib
        # already renders in that same screen region
        tick_labels = [f"{int(r)}.  {lbl}" if config.show_rank else lbl
                       for r, lbl in zip(frame["rank"], labels)]

        if config.orientation == Orientation.HORIZONTAL:
            bars = ax.barh(positions, values, color=bar_colors, height=config.bar_width_ratio)
            ax.set_xlim(0, max_value + value_area)
            ax.set_yticks(positions)
            ax.set_yticklabels(tick_labels, color=text_color, fontsize=config.label_size_px * 0.6)
            ax.xaxis.set_ticks_position("top")  # matches the sports-standings style: scale reads top-down
            ax.xaxis.set_label_position("top")
        else:
            bars = ax.bar(positions, values, color=bar_colors, width=config.bar_width_ratio)
            ax.set_ylim(0, max_value + value_area)
            ax.set_xticks(positions)
            ax.set_xticklabels(tick_labels, rotation=45, ha="right", color=text_color, fontsize=config.label_size_px * 0.6)

        for bar, row in zip(bars, frame.itertuples(index=False)):
            value_text_end = bar.get_width() if config.orientation == Orientation.HORIZONTAL else bar.get_height()
            if config.show_value:
                # a fixed points offset (not a fraction of max_value) so
                # the gap to the bar tip stays visually consistent
                # regardless of the data's scale, and lines up with the
                # image's own points-offset placement below instead of
                # drifting into it
                text = format_value(row.value, config.value_format, config.value_decimal_places)
                if config.orientation == Orientation.HORIZONTAL:
                    ax.annotate(text, (value_text_end, bar.get_y() + bar.get_height() / 2),
                                xytext=(10, 0), textcoords="offset points",
                                va="center", ha="left", color=text_color, fontsize=config.label_size_px * 0.6,
                                fontweight="bold")
                else:
                    ax.annotate(text, (bar.get_x() + bar.get_width() / 2, value_text_end),
                                xytext=(0, 10), textcoords="offset points",
                                ha="center", va="bottom", color=text_color, fontsize=config.label_size_px * 0.6,
                                fontweight="bold")

            if resolver is not None:
                avatar = resolver.resolve(row.entity, row.image_url)
                imagebox = OffsetImage(np.asarray(avatar), zoom=24 / avatar.width)
                # placed further out than the value label (both anchored
                # to the same bar-tip point, both offset in points so the
                # gap between them stays fixed regardless of data scale)
                # so it reads as "this bar's entity" the way a crest/logo
                # sits at the end of a sports-standings race, without
                # overlapping the value text
                if config.orientation == Orientation.HORIZONTAL:
                    ab = AnnotationBbox(imagebox, (value_text_end, bar.get_y() + bar.get_height() / 2),
                                         xybox=(50, 0), xycoords="data", boxcoords="offset points",
                                         frameon=False, box_alignment=(0.5, 0.5))
                else:
                    ab = AnnotationBbox(imagebox, (bar.get_x() + bar.get_width() / 2, value_text_end),
                                         xybox=(0, 50), xycoords="data", boxcoords="offset points",
                                         frameon=False, box_alignment=(0.5, 0.5))
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

        period_label = _period_label(frame_index, config.mapping.value_columns)
        fig.suptitle(
            f"{config.title}  :  {period_label}" if config.title else period_label,
            color=text_color, fontsize=config.label_size_px * 1.2, fontweight="bold",
        )
        if config.subtitle:
            ax.set_title(config.subtitle, color=secondary_text_color, fontsize=config.label_size_px * 0.7, loc="left")
        if config.data_source_label:
            fig.text(0.99, 0.01, f"Source: {config.data_source_label}", ha="right", va="bottom",
                      color=secondary_text_color, fontsize=config.label_size_px * 0.5)

        fig.tight_layout(rect=(0, 0.03, 1, 0.94))

        if watermark is not None:
            wm_h, wm_w = watermark.shape[0], watermark.shape[1]
            x, y = _watermark_anchor(config.watermark_position, width_px, height_px, wm_w, wm_h)
            fig.figimage(watermark, xo=x, yo=y, alpha=None, zorder=10)

        frame_path = os.path.join(output_dir, f"frame_{i:05d}.png")
        fig.savefig(frame_path, facecolor=config.background_color,
                    transparent=config.transparent_background)
        plt.close(fig)
        paths.append(frame_path)

    return paths
