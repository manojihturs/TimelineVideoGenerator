import { useRaceConfig } from '../../../hooks/useRaceConfig'
import type { SocialPreset, StylePreset } from '../../../models/RaceConfig'
import { Field, PanelSection, SelectInput } from '../FormControls'

const STYLE_PRESET_OPTIONS: { value: StylePreset; label: string }[] = [
  { value: 'custom', label: 'Custom (use settings below)' },
  { value: 'sports_light', label: 'Sports Light — white background, compact standings feel' },
  { value: 'narrative_dark', label: 'Narrative Dark — bold oversized text, historical-timeline feel' },
  { value: 'pastel_soft', label: 'Pastel Soft — muted palette, gentle data-story feel' },
]

const SOCIAL_PRESET_OPTIONS: { value: SocialPreset; label: string }[] = [
  { value: 'none', label: 'None (use Resolution/Orientation below)' },
  { value: 'youtube_shorts', label: 'YouTube Shorts (1080x1920, ~60s)' },
  { value: 'tiktok', label: 'TikTok (1080x1920, ~60s)' },
  { value: 'instagram_reels', label: 'Instagram Reels (1080x1920, ~90s)' },
  { value: 'youtube_landscape', label: 'YouTube Landscape (1920x1080)' },
]

export function StylePanel() {
  const { config, updateConfig } = useRaceConfig()
  return (
    <PanelSection title="Style & platform presets">
      <Field label="Visual style">
        <SelectInput value={config.style_preset} onChange={(value) => updateConfig({ style_preset: value })} options={STYLE_PRESET_OPTIONS} />
      </Field>
      <Field label="Social preset">
        <SelectInput value={config.social_preset} onChange={(value) => updateConfig({ social_preset: value })} options={SOCIAL_PRESET_OPTIONS} />
      </Field>
      {config.social_preset !== 'none' && (
        <p className="mt-1 text-xs text-gray-500">
          Overrides Resolution and Orientation in the Export section below at render time.
        </p>
      )}
    </PanelSection>
  )
}
