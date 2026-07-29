"""The single object that fully describes one race. Every setting in the
frontend's PropertyPanel maps to exactly one field here — render code
should never hardcode a value that belongs in this model."""
from enum import Enum

from pydantic import BaseModel


class SortDirection(str, Enum):
    ASCENDING = "ascending"
    DESCENDING = "descending"


class Orientation(str, Enum):
    HORIZONTAL = "horizontal"   # classic racing bars, growing left-to-right
    VERTICAL = "vertical"       # racing columns, growing bottom-to-top


class ColorMode(str, Enum):
    SINGLE = "single"
    CATEGORY = "category"
    RANDOM = "random"
    CUSTOM = "custom"


class ValueFormat(str, Enum):
    NUMBER = "number"
    CURRENCY = "currency"
    PERCENTAGE = "percentage"
    THOUSANDS = "thousands"
    MILLIONS = "millions"
    BILLIONS = "billions"


class Interpolation(str, Enum):
    LINEAR = "linear"
    EASE_IN_OUT = "easeInOut"
    EASE_IN = "easeIn"
    EASE_OUT = "easeOut"


class ExportFormat(str, Enum):
    MP4 = "mp4"
    GIF = "gif"
    PNG_FRAMES = "png_frames"


class Resolution(str, Enum):
    HD_1080P = "1080p"
    QHD_1440P = "1440p"
    UHD_4K = "4k"
    VERTICAL_1080X1920 = "vertical_1080x1920"   # Shorts/Reels/TikTok


class ColumnMapping(BaseModel):
    entity_column: str
    category_column: str | None = None
    image_column: str | None = None
    timeline_start_column: str
    timeline_end_column: str
    value_columns: list[str]


class RaceConfig(BaseModel):
    dataset_id: str
    mapping: ColumnMapping

    title: str = ""
    subtitle: str = ""
    data_source_label: str = ""

    fps: int = 30
    animation_speed: float = 1.0
    transition_duration_ms: int = 500
    interpolation: Interpolation = Interpolation.EASE_IN_OUT

    bar_count: int = 10
    sort_direction: SortDirection = SortDirection.DESCENDING
    orientation: Orientation = Orientation.HORIZONTAL
    bar_color_mode: ColorMode = ColorMode.CATEGORY
    single_color: str = "#7C3AED"
    custom_color_map: dict[str, str] = {}
    bar_width_ratio: float = 0.8

    background_color: str = "#0B0F14"
    font_family: str = "Inter"
    label_size_px: int = 16

    show_images: bool = True
    show_category: bool = True
    show_rank: bool = True
    show_value: bool = True
    show_axis: bool = True
    show_grid: bool = False
    smooth_animation: bool = True

    value_format: ValueFormat = ValueFormat.NUMBER
    value_decimal_places: int = 0
    date_format: str = "YYYY-MM"

    export_format: ExportFormat = ExportFormat.MP4
    resolution: Resolution = Resolution.HD_1080P
    transparent_background: bool = False
