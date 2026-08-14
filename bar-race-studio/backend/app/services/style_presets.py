"""Applying a StylePreset overrides background/font/label-size (and
which bar palette race_renderer uses) — two original looks, not copied
from any reference: SPORTS_LIGHT (crisp, white, compact) and
NARRATIVE_DARK (bold, dark, oversized text for a historical-timeline
feel). Neither reuses the other's palette, so switching actually looks
different rather than just inverting one color."""
from app.models.config import RaceConfig, StylePreset

# Two independently-designed palettes — not variations of each other.
# Each grown to 15 maximally-distinct entries (matching race_renderer's
# DEFAULT_PALETTE) so bar_count up to the UI's max of 50 doesn't wrap
# back onto a color already in use for a while — 10 entries meant any
# preset started repeating colors well before that.
SPORTS_LIGHT_PALETTE = [
    "#2563EB", "#DC2626", "#059669", "#D97706", "#4F46E5",
    "#0891B2", "#DB2777", "#65A30D", "#EA580C", "#7C3AED",
    "#CA8A04", "#0D9488", "#C026D3", "#E11D48", "#92400E",
]

NARRATIVE_DARK_PALETTE = [
    "#FB7185", "#38BDF8", "#FACC15", "#34D399", "#C084FC",
    "#FB923C", "#22D3EE", "#A3E635", "#F472B6", "#818CF8",
    "#4ADE80", "#2DD4BF", "#60A5FA", "#A78BFA", "#E879F9",
]

# soft/muted, not just SPORTS_LIGHT_PALETTE lightened — chosen from a
# different hue set entirely so it reads as its own look
PASTEL_SOFT_PALETTE = [
    "#8FB3E8", "#F2A6A6", "#9BD8B8", "#F5C77E", "#B79FE0",
    "#F0A8C9", "#7FCFC7", "#E0B583", "#A8C7E0", "#D3A6D9",
    "#D2DF90", "#97DF90", "#90D2DF", "#9092DF", "#DF90CF",
]

STYLE_PRESET_PALETTES: dict[StylePreset, list[str]] = {
    StylePreset.SPORTS_LIGHT: SPORTS_LIGHT_PALETTE,
    StylePreset.NARRATIVE_DARK: NARRATIVE_DARK_PALETTE,
    StylePreset.PASTEL_SOFT: PASTEL_SOFT_PALETTE,
}

_STYLE_PRESET_FIELDS: dict[StylePreset, dict] = {
    StylePreset.SPORTS_LIGHT: {
        "background_color": "#FFFFFF",
        "font_family": "Inter",
        "label_size_px": 16,
    },
    StylePreset.NARRATIVE_DARK: {
        "background_color": "#0F172A",
        "font_family": "Inter",
        "label_size_px": 22,  # oversized, readable-at-a-glance text for the historical-timeline feel
    },
    StylePreset.PASTEL_SOFT: {
        "background_color": "#FAF7F2",  # warm off-white, softer than pure white
        "font_family": "Inter",
        "label_size_px": 17,
    },
}


def apply_style_preset(config: RaceConfig) -> RaceConfig:
    if config.style_preset == StylePreset.CUSTOM:
        return config
    return config.model_copy(update=_STYLE_PRESET_FIELDS[config.style_preset])


def palette_for(config: RaceConfig) -> list[str]:
    return STYLE_PRESET_PALETTES.get(config.style_preset, SPORTS_LIGHT_PALETTE)
