"""Applying a SocialPreset just sets a few underlying RaceConfig fields —
this is the one place that mapping lives, so it can't drift out of sync
with itself."""
from app.models.config import Orientation, RaceConfig, Resolution, SocialPreset

# (resolution, orientation, suggested_max_seconds) — the duration is a
# suggestion surfaced to the UI, not enforced by the renderer.
#
# Orientation here means bar orientation, not canvas orientation. Portrait
# short-form video (Shorts/TikTok/Reels) still conventionally races
# left-to-right horizontal bars on a taller canvas — switching to vertical
# columns just because the canvas is portrait wastes most of the frame as
# empty whitespace above the bars and reads as a different, worse chart type.
SOCIAL_PRESET_SETTINGS: dict[SocialPreset, tuple[Resolution, Orientation, int]] = {
    SocialPreset.YOUTUBE_SHORTS: (Resolution.VERTICAL_1080X1920, Orientation.HORIZONTAL, 60),
    SocialPreset.TIKTOK: (Resolution.VERTICAL_1080X1920, Orientation.HORIZONTAL, 60),
    SocialPreset.INSTAGRAM_REELS: (Resolution.VERTICAL_1080X1920, Orientation.HORIZONTAL, 90),
    SocialPreset.YOUTUBE_LANDSCAPE: (Resolution.HD_1080P, Orientation.HORIZONTAL, 600),
}


def apply_social_preset(config: RaceConfig) -> RaceConfig:
    """Returns a new RaceConfig with resolution/orientation overridden to
    match config.social_preset, if it's set to anything other than NONE.
    Suggested duration is not applied here — it's informational only,
    surfaced by the frontend preset picker."""
    if config.social_preset == SocialPreset.NONE:
        return config
    resolution, orientation, _suggested_seconds = SOCIAL_PRESET_SETTINGS[config.social_preset]
    return config.model_copy(update={"resolution": resolution, "orientation": orientation})
