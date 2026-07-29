import { useRaceConfig } from '../../../hooks/useRaceConfig'
import { Field, PanelSection, TextInput } from '../FormControls'

export function ChartTextPanel() {
  const { config, updateConfig } = useRaceConfig()
  return (
    <PanelSection title="Chart text">
      <Field label="Title">
        <TextInput value={config.title} onChange={(e) => updateConfig({ title: e.target.value })} />
      </Field>
      <Field label="Subtitle">
        <TextInput value={config.subtitle} onChange={(e) => updateConfig({ subtitle: e.target.value })} />
      </Field>
      <Field label="Data source">
        <TextInput
          value={config.data_source_label}
          onChange={(e) => updateConfig({ data_source_label: e.target.value })}
        />
      </Field>
    </PanelSection>
  )
}
