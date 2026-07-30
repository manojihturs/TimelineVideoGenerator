// Mirrors backend/app/models/config.py — every field here maps to one
// control in the PropertyPanel. Keep the two in sync by hand for now;
// generating this from a shared JSON schema is a later improvement.

export type SortDirection = 'ascending' | 'descending'
export type Orientation = 'horizontal' | 'vertical'
export type ColorMode = 'single' | 'category' | 'random' | 'custom'
export type ValueFormat = 'number' | 'currency' | 'percentage' | 'thousands' | 'millions' | 'billions'
export type Interpolation = 'linear' | 'easeInOut' | 'easeIn' | 'easeOut'
export type ExportFormat = 'mp4' | 'gif' | 'png_frames'
export type Resolution = '1080p' | '1440p' | '4k' | 'vertical_1080x1920'
export type SocialPreset = 'none' | 'youtube_shorts' | 'tiktok' | 'instagram_reels' | 'youtube_landscape'
export type StylePreset = 'custom' | 'sports_light' | 'narrative_dark'
export type WatermarkPosition = 'top_left' | 'top_right' | 'bottom_left' | 'bottom_right'

export interface ColumnMapping {
  entity_column: string
  category_column: string | null
  image_column: string | null
  timeline_start_column: string
  timeline_end_column: string
  value_columns: string[]
}

export interface RaceConfig {
  dataset_id: string
  mapping: ColumnMapping

  title: string
  subtitle: string
  data_source_label: string

  fps: number
  animation_speed: number
  transition_duration_ms: number
  interpolation: Interpolation

  bar_count: number
  sort_direction: SortDirection
  orientation: Orientation
  bar_color_mode: ColorMode
  single_color: string
  custom_color_map: Record<string, string>
  bar_width_ratio: number

  background_color: string
  font_family: string
  label_size_px: number

  show_images: boolean
  show_category: boolean
  show_rank: boolean
  show_value: boolean
  show_axis: boolean
  show_grid: boolean
  smooth_animation: boolean

  value_format: ValueFormat
  value_decimal_places: number
  date_format: string

  export_format: ExportFormat
  resolution: Resolution
  transparent_background: boolean
  social_preset: SocialPreset
  style_preset: StylePreset

  watermark_asset_id: string | null
  watermark_opacity: number
  watermark_position: WatermarkPosition
  watermark_scale: number

  music_asset_id: string | null
  music_volume: number
}

export function createDefaultRaceConfig(mapping: ColumnMapping): RaceConfig {
  return {
    dataset_id: '',
    mapping,
    title: '',
    subtitle: '',
    data_source_label: '',
    fps: 30,
    animation_speed: 1,
    transition_duration_ms: 500,
    interpolation: 'easeInOut',
    bar_count: 10,
    sort_direction: 'descending',
    orientation: 'horizontal',
    bar_color_mode: 'category',
    single_color: '#7C3AED',
    custom_color_map: {},
    bar_width_ratio: 0.8,
    background_color: '#FFFFFF',
    font_family: 'Inter',
    label_size_px: 16,
    show_images: true,
    show_category: true,
    show_rank: true,
    show_value: true,
    show_axis: true,
    show_grid: false,
    smooth_animation: true,
    value_format: 'number',
    value_decimal_places: 0,
    date_format: 'YYYY-MM',
    export_format: 'mp4',
    resolution: '1080p',
    transparent_background: false,
    social_preset: 'none',
    style_preset: 'custom',
    watermark_asset_id: null,
    watermark_opacity: 0.7,
    watermark_position: 'bottom_right',
    watermark_scale: 0.12,
    music_asset_id: null,
    music_volume: 0.5,
  }
}
