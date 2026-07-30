"""Applying a StylePreset overrides background/font/label-size (and
which bar palette race_renderer uses) — two original looks, not copied
from any reference: SPORTS_LIGHT (crisp, white, compact) and
NARRATIVE_DARK (bold, dark, oversized text for a historical-timeline
feel). Neither reuses the other's palette, so switching actually looks
different rather than just inverting one color."""
from app.models.config import RaceConfig, StylePreset

# Two independently-designed palettes — not variations of each other.
SPORTS_LIGHT_PALETTE = [
    "#2563EB", "#DC2626", "#059669", "#D97706", "#4F46E5",
    "#0891B2", "#DB2777", "#65A30D", "#EA580C", "#7C3AED",
]

NARRATIVE_DARK_PALETTE = [
    "#FB7185", "#38BDF8", "#FACC15", "#34D399", "#C084FC",
    "#FB923C", "#22D3EE", "#A3E635", "#F472B6", "#818CF8",
]

STYLE_PRESET_PALETTES: dict[StylePreset, list[str]] = {
    StylePreset.SPORTS_LIGHT: SPORTS_LIGHT_PALETTE,
    StylePreset.NARRATIVE_DARK: NARRATIVE_DARK_PALETTE,
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
}


def apply_style_preset(config: RaceConfig) -> RaceConfig:
    if config.style_preset == StylePreset.CUSTOM:
        return config
    return config.model_copy(update=_STYLE_PRESET_FIELDS[config.style_preset])


def palette_for(config: RaceConfig) -> list[str]:
    return STYLE_PRESET_PALETTES.get(config.style_preset, SPORTS_LIGHT_PALETTE)
