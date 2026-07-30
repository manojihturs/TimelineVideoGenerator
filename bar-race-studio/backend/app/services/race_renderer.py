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
from matplotlib.patches import Circle
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


def _hex_to_rgb(hex_color: str) -> tuple[float, float, float]:
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _lighten(hex_color: str, amount: float) -> tuple[float, float, float]:
    """Blends hex_color toward white by `amount` (0-1) — the second stop
    of each bar's duotone gradient, derived from its own base color
    rather than an unrelated second color, so the gradient still reads
    as "one entity's bar" rather than two colors collided together."""
    r, g, b = _hex_to_rgb(hex_color)
    return r + (1 - r) * amount, g + (1 - g) * amount, b + (1 - b) * amount


def _gradient_array(color_a: tuple[float, float, float], color_b: tuple[float, float, float], steps: int = 128) -> np.ndarray:
    """An (steps, 1, 3) image array for imshow — a smooth left-to-right
    (or bottom-to-top) blend between two colors, forming each bar's
    multi-color fill."""
    t = np.linspace(0, 1, steps).reshape(-1, 1)
    a, b = np.array(color_a), np.array(color_b)
    return (a[None, :] * (1 - t) + b[None, :] * t).reshape(steps, 1, 3)


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

        half = config.bar_width_ratio / 2

        for pos, value, entity, category, image_url, base_color in zip(
            positions, values, frame["entity"], frame["category"], frame["image_url"], bar_colors,
        ):
            if value <= 0:
                continue

            # rounded "pill" bar: a horizontal(/vertical) color-gradient
            # fill clipped to the bar's rectangle, plus a filled circle
            # at each end sized to the bar's own thickness — the circles
            # are what make the ends read as rounded instead of square,
            # without matplotlib's FancyBboxPatch rounding-size ambiguity
            # (its units depend on the transform in a way that's easy to
            # get subtly wrong against wildly different x/y data scales).
            gradient_end = _lighten(base_color, 0.4)
            if config.orientation == Orientation.HORIZONTAL:
                gradient = _gradient_array(_hex_to_rgb(base_color), gradient_end)
                ax.imshow(gradient, extent=(0, value, pos - half, pos + half),
                          aspect="auto", zorder=2, interpolation="bilinear")
                ax.add_patch(Circle((0, pos), half, color=base_color, zorder=2, linewidth=0))
                ax.add_patch(Circle((value, pos), half, color=gradient_end, zorder=2, linewidth=0))
            else:
                gradient = _gradient_array(_hex_to_rgb(base_color), gradient_end).transpose(1, 0, 2)
                ax.imshow(gradient, extent=(pos - half, pos + half, 0, value),
                          aspect="auto", zorder=2, interpolation="bilinear")
                ax.add_patch(Circle((pos, 0), half, color=base_color, zorder=2, linewidth=0))
                ax.add_patch(Circle((pos, value), half, color=gradient_end, zorder=2, linewidth=0))

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

            if resolver is not None:
                avatar = resolver.resolve(entity, image_url)
                # inside the bar, near its start. OffsetImage's zoom is a
                # points-space scale factor, NOT a data-coordinate size —
                # deriving it from `half` (a data-space bar-thickness
                # value, e.g. ~0.3-0.5) previously shrank the icon to a
                # sliver of a pixel. A fixed point diameter, scaled by
                # label_size_px like the rest of the chart's text, is
                # what actually produces a visible, consistently-sized
                # icon regardless of the data's value scale.
                icon_diameter_pt = config.label_size_px * 1.8
                imagebox = OffsetImage(np.asarray(avatar), zoom=icon_diameter_pt / avatar.width)
                inset_offset = half * 1.15  # just past the rounded end-cap, inside the fill
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

        if config.title:
            fig.suptitle(config.title, color=text_color, fontsize=config.label_size_px * 1.2, fontweight="bold")
        if config.subtitle:
            ax.set_title(config.subtitle, color=secondary_text_color, fontsize=config.label_size_px * 0.7, loc="left")
        if config.data_source_label:
            fig.text(0.99, 0.01, f"Source: {config.data_source_label}", ha="right", va="bottom",
                      color=secondary_text_color, fontsize=config.label_size_px * 0.5)

        # large bottom-right period/year watermark, separate from the
        # title — the "current point in time" reads at a glance the way
        # a big stylized year label does in historical-timeline-style
        # bar chart races, rather than being buried in the title text
        period_label = _period_label(frame_index, config.mapping.value_columns)
        fig.text(0.985, 0.06, period_label, ha="right", va="bottom",
                  color=text_color, fontsize=config.label_size_px * 2.2, fontweight="bold", alpha=0.85)

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
