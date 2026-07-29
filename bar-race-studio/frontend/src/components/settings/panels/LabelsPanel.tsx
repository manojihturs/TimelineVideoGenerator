import { useRaceConfig } from '../../../hooks/useRaceConfig'
import { ColorInput, Field, NumberInput, PanelSection, TextInput, ToggleInput } from '../FormControls'

export function LabelsPanel() {
  const { config, updateConfig } = useRaceConfig()
  return (
    <PanelSection title="Labels & display">
      <ToggleInput label="Show rank" checked={config.show_rank} onChange={(v) => updateConfig({ show_rank: v })} />
      <ToggleInput label="Show value" checked={config.show_value} onChange={(v) => updateConfig({ show_value: v })} />
      <ToggleInput label="Show category" checked={config.show_category} onChange={(v) => updateConfig({ show_category: v })} />
      <ToggleInput label="Show axis" checked={config.show_axis} onChange={(v) => updateConfig({ show_axis: v })} />
      <ToggleInput label="Show grid" checked={config.show_grid} onChange={(v) => updateConfig({ show_grid: v })} />
      <Field label="Font family">
        <TextInput value={config.font_family} onChange={(e) => updateConfig({ font_family: e.target.value })} />
      </Field>
      <Field label="Label size (px)">
        <NumberInput
          min={8}
          max={72}
          value={config.label_size_px}
          onChange={(e) => updateConfig({ label_size_px: Number(e.target.value) })}
        />
      </Field>
      <Field label="Background color">
        <ColorInput value={config.background_color} onChange={(e) => updateConfig({ background_color: e.target.value })} />
      </Field>
    </PanelSection>
  )
}
