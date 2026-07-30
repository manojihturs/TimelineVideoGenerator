import type { RaceConfig, StylePreset } from '../models/RaceConfig'

// Mirrors backend/app/services/style_presets.py — same two independently
// designed looks, same override-only behavior (CUSTOM leaves the base
// config's own background_color/font_family/label_size_px alone).
const STYLE_PRESET_FIELDS: Record<Exclude<StylePreset, 'custom'>, Pick<RaceConfig, 'background_color' | 'font_family' | 'label_size_px'>> = {
  sports_light: { background_color: '#FFFFFF', font_family: 'Inter', label_size_px: 16 },
  narrative_dark: { background_color: '#0F172A', font_family: 'Inter', label_size_px: 22 },
}

const SPORTS_LIGHT_PALETTE = [
  '#2563EB', '#DC2626', '#059669', '#D97706', '#4F46E5',
  '#0891B2', '#DB2777', '#65A30D', '#EA580C', '#7C3AED',
]

const NARRATIVE_DARK_PALETTE = [
  '#FB7185', '#38BDF8', '#FACC15', '#34D399', '#C084FC',
  '#FB923C', '#22D3EE', '#A3E635', '#F472B6', '#818CF8',
]

const DEFAULT_PALETTE = [
  '#2563EB', '#DC2626', '#059669', '#D97706', '#7C3AED',
  '#0891B2', '#DB2777', '#65A30D', '#EA580C', '#4F46E5',
]

const STYLE_PRESET_PALETTES: Record<StylePreset, string[]> = {
  custom: DEFAULT_PALETTE,
  sports_light: SPORTS_LIGHT_PALETTE,
  narrative_dark: NARRATIVE_DARK_PALETTE,
}

/** The config the preview should actually render with — style_preset
 * overrides applied client-side, the same way apply_style_preset does
 * server-side at render time, so what you see while editing matches
 * what exporting will actually produce. */
export function withStylePreset(config: RaceConfig): RaceConfig {
  if (config.style_preset === 'custom') return config
  return { ...config, ...STYLE_PRESET_FIELDS[config.style_preset] }
}

export function paletteForStyle(stylePreset: StylePreset): string[] {
  return STYLE_PRESET_PALETTES[stylePreset]
}

/** Perceptual luminance decides light vs. dark text/gridlines against a
 * given background — mirrors race_renderer.py's _contrast_text_color. */
export function contrastTextColors(backgroundHex: string): { text: string; secondary: string; grid: string } {
  const hex = backgroundHex.replace('#', '')
  const r = parseInt(hex.slice(0, 2), 16)
  const g = parseInt(hex.slice(2, 4), 16)
  const b = parseInt(hex.slice(4, 6), 16)
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
  if (luminance > 0.5) {
    return { text: '#111827', secondary: '#4b5563', grid: '#d1d5db' }
  }
  return { text: '#f3f4f6', secondary: '#9ca3af', grid: '#374151' }
}
