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
from app.api.assets import resolve_asset_path

CATEGORY_PALETTE = [
    "#7C3AED", "#2563EB", "#059669", "#D97706", "#DC2626",
    "#DB2777", "#0891B2", "#65A30D", "#9333EA", "#EA580C",
]


def _resolve_colors(ranked_df: pd.DataFrame, config: RaceConfig) -> dict[str, str]:
    """entity/category -> hex color, resolved once for the whole render
    so a given entity/category keeps the same color across every frame."""
    if config.bar_color_mode == ColorMode.SINGLE:
        keys = ranked_df["entity"].unique()
        return {k: config.single_color for k in keys}

    if config.bar_color_mode == ColorMode.CUSTOM:
        keys = ranked_df["entity"].unique()
        return {k: config.custom_color_map.get(k, CATEGORY_PALETTE[0]) for k in keys}

    if config.bar_color_mode == ColorMode.RANDOM:
        rng = np.random.default_rng(seed=42)  # deterministic across frames/re-renders
        keys = sorted(ranked_df["entity"].unique())
        return {k: CATEGORY_PALETTE[rng.integers(0, len(CATEGORY_PALETTE))] for k in keys}

    # CATEGORY (default): color by category if present, else fall back to entity
    group_col = "category" if ranked_df["category"].notna().any() else "entity"
    keys = sorted(ranked_df[group_col].dropna().unique())
    color_by_group = {k: CATEGORY_PALETTE[i % len(CATEGORY_PALETTE)] for i, k in enumerate(keys)}
    return {
        row.entity: color_by_group.get(getattr(row, group_col), CATEGORY_PALETTE[0])
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
            bar_colors.append(colors.get(row.entity, CATEGORY_PALETTE[0]))

        positions = np.arange(len(frame))[::-1]  # rank 1 at top/right

        if config.orientation == Orientation.HORIZONTAL:
            bars = ax.barh(positions, values, color=bar_colors, height=config.bar_width_ratio)
            ax.set_xlim(0, max_value * 1.15)
            ax.set_yticks(positions)
            ax.set_yticklabels(labels if not config.show_images else [])
        else:
            bars = ax.bar(positions, values, color=bar_colors, width=config.bar_width_ratio)
            ax.set_ylim(0, max_value * 1.15)
            ax.set_xticks(positions)
            ax.set_xticklabels(labels if not config.show_images else [], rotation=45, ha="right")

        for bar, row in zip(bars, frame.itertuples(index=False)):
            if config.show_value:
                text = format_value(row.value, config.value_format, config.value_decimal_places)
                if config.orientation == Orientation.HORIZONTAL:
                    ax.text(bar.get_width() + max_value * 0.01, bar.get_y() + bar.get_height() / 2,
                            text, va="center", ha="left", color="#e5e7eb", fontsize=config.label_size_px * 0.6)
                else:
                    ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + max_value * 0.01,
                            text, ha="center", va="bottom", color="#e5e7eb", fontsize=config.label_size_px * 0.6)

            if resolver is not None:
                avatar = resolver.resolve(row.entity, row.image_url)
                imagebox = OffsetImage(np.asarray(avatar), zoom=24 / avatar.width)
                if config.orientation == Orientation.HORIZONTAL:
                    ab = AnnotationBbox(imagebox, (0, bar.get_y() + bar.get_height() / 2),
                                         xybox=(-24, 0), xycoords="data", boxcoords="offset points",
                                         frameon=False, box_alignment=(1, 0.5))
                else:
                    ab = AnnotationBbox(imagebox, (bar.get_x() + bar.get_width() / 2, 0),
                                         xybox=(0, -24), xycoords="data", boxcoords="offset points",
                                         frameon=False, box_alignment=(0.5, 1))
                ax.add_artist(ab)

            if config.show_rank:
                rank_text = str(int(row.rank))
                if config.orientation == Orientation.HORIZONTAL:
                    ax.text(-max_value * 0.02, bar.get_y() + bar.get_height() / 2, rank_text,
                            va="center", ha="right", color="#9ca3af", fontsize=config.label_size_px * 0.6,
                            fontweight="bold")

        if not config.show_axis:
            ax.set_xticks([]) if config.orientation == Orientation.HORIZONTAL else ax.set_yticks([])
            for spine in ax.spines.values():
                spine.set_visible(False)
        if config.show_grid:
            ax.grid(True, axis="x" if config.orientation == Orientation.HORIZONTAL else "y",
                    color="#374151", linewidth=0.5, alpha=0.5)
        else:
            ax.grid(False)

        ax.tick_params(colors="#e5e7eb", labelsize=config.label_size_px * 0.55)

        title_parts = []
        if config.title:
            title_parts.append(config.title)
        period_label = _period_label(frame_index, config.mapping.value_columns)
        fig.suptitle(
            f"{config.title}  —  {period_label}" if config.title else period_label,
            color="#f3f4f6", fontsize=config.label_size_px * 1.2, fontweight="bold",
        )
        if config.subtitle:
            ax.set_title(config.subtitle, color="#9ca3af", fontsize=config.label_size_px * 0.7, loc="left")
        if config.data_source_label:
            fig.text(0.99, 0.01, f"Source: {config.data_source_label}", ha="right", va="bottom",
                      color="#6b7280", fontsize=config.label_size_px * 0.5)

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
