import { useRaceConfig } from '../../../hooks/useRaceConfig'
import type { ExportFormat, Resolution } from '../../../models/RaceConfig'
import { Field, PanelSection, SelectInput, ToggleInput } from '../FormControls'

const FORMAT_OPTIONS: { value: ExportFormat; label: string }[] = [
  { value: 'mp4', label: 'MP4' },
  { value: 'gif', label: 'GIF' },
  { value: 'png_frames', label: 'PNG frames (zip)' },
]

const RESOLUTION_OPTIONS: { value: Resolution; label: string }[] = [
  { value: '1080p', label: '1080p (1920x1080)' },
  { value: '1440p', label: '1440p (2560x1440)' },
  { value: '4k', label: '4K (3840x2160)' },
  { value: 'vertical_1080x1920', label: 'Vertical (1080x1920) — Shorts/Reels/TikTok' },
]

export function ExportPanel() {
  const { config, updateConfig } = useRaceConfig()
  return (
    <PanelSection title="Export">
      <Field label="Format">
        <SelectInput value={config.export_format} onChange={(value) => updateConfig({ export_format: value })} options={FORMAT_OPTIONS} />
      </Field>
      <Field label="Resolution">
        <SelectInput value={config.resolution} onChange={(value) => updateConfig({ resolution: value })} options={RESOLUTION_OPTIONS} />
      </Field>
      <ToggleInput
        label="Transparent background"
        checked={config.transparent_background}
        onChange={(v) => updateConfig({ transparent_background: v })}
      />
    </PanelSection>
  )
}
