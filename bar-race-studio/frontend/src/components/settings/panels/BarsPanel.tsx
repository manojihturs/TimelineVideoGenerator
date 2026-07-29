import { useRaceConfig } from '../../../hooks/useRaceConfig'
import type { ColorMode, Orientation, SortDirection } from '../../../models/RaceConfig'
import { ColorInput, Field, NumberInput, PanelSection, SelectInput } from '../FormControls'

const SORT_OPTIONS: { value: SortDirection; label: string }[] = [
  { value: 'descending', label: 'Descending (largest first)' },
  { value: 'ascending', label: 'Ascending (smallest first)' },
]

const ORIENTATION_OPTIONS: { value: Orientation; label: string }[] = [
  { value: 'horizontal', label: 'Horizontal (racing bars)' },
  { value: 'vertical', label: 'Vertical (racing columns)' },
]

const COLOR_MODE_OPTIONS: { value: ColorMode; label: string }[] = [
  { value: 'category', label: 'By category' },
  { value: 'single', label: 'Single color' },
  { value: 'random', label: 'Random' },
  { value: 'custom', label: 'Custom (per entity/category)' },
]

export function BarsPanel() {
  const { config, updateConfig } = useRaceConfig()
  return (
    <PanelSection title="Bars">
      <Field label="Number of bars">
        <NumberInput
          min={1}
          max={50}
          value={config.bar_count}
          onChange={(e) => updateConfig({ bar_count: Number(e.target.value) })}
        />
      </Field>
      <Field label="Sort">
        <SelectInput value={config.sort_direction} onChange={(value) => updateConfig({ sort_direction: value })} options={SORT_OPTIONS} />
      </Field>
      <Field label="Orientation">
        <SelectInput value={config.orientation} onChange={(value) => updateConfig({ orientation: value })} options={ORIENTATION_OPTIONS} />
      </Field>
      <Field label="Bar color mode">
        <SelectInput value={config.bar_color_mode} onChange={(value) => updateConfig({ bar_color_mode: value })} options={COLOR_MODE_OPTIONS} />
      </Field>
      {config.bar_color_mode === 'single' && (
        <Field label="Bar color">
          <ColorInput value={config.single_color} onChange={(e) => updateConfig({ single_color: e.target.value })} />
        </Field>
      )}
      <Field label="Bar width">
        <NumberInput
          min={0.1}
          max={1}
          step={0.05}
          value={config.bar_width_ratio}
          onChange={(e) => updateConfig({ bar_width_ratio: Number(e.target.value) })}
        />
      </Field>
    </PanelSection>
  )
}
