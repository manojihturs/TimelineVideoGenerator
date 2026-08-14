import { useRaceConfig } from '../../../hooks/useRaceConfig'
import { Field, PanelSection, TextInput } from '../FormControls'

export function ChartTextPanel() {
  const { config, updateConfig } = useRaceConfig()
  return (
    <PanelSection title="Chart text">
      <Field label="Title" required hint="Required to export — shown on the video and cited for YouTube's monetization policy.">
        <TextInput value={config.title} onChange={(e) => updateConfig({ title: e.target.value })} />
      </Field>
      <Field label="Subtitle">
        <TextInput value={config.subtitle} onChange={(e) => updateConfig({ subtitle: e.target.value })} />
      </Field>
      <Field label="Data source" required hint="Required to export — cites where the data came from.">
        <TextInput
          value={config.data_source_label}
          onChange={(e) => updateConfig({ data_source_label: e.target.value })}
        />
      </Field>
    </PanelSection>
  )
}
