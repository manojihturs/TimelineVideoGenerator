import { useRaceConfig } from '../../../hooks/useRaceConfig'
import type { ValueFormat } from '../../../models/RaceConfig'
import { Field, NumberInput, PanelSection, SelectInput, TextInput } from '../FormControls'

const VALUE_FORMAT_OPTIONS: { value: ValueFormat; label: string }[] = [
  { value: 'number', label: 'Number' },
  { value: 'currency', label: 'Currency' },
  { value: 'percentage', label: 'Percentage' },
  { value: 'thousands', label: 'Thousands (K)' },
  { value: 'millions', label: 'Millions (M)' },
  { value: 'billions', label: 'Billions (B)' },
]

export function FormattingPanel() {
  const { config, updateConfig } = useRaceConfig()
  return (
    <PanelSection title="Value & date formatting">
      <Field label="Value format">
        <SelectInput value={config.value_format} onChange={(value) => updateConfig({ value_format: value })} options={VALUE_FORMAT_OPTIONS} />
      </Field>
      <Field label="Decimal places">
        <NumberInput
          min={0}
          max={6}
          value={config.value_decimal_places}
          onChange={(e) => updateConfig({ value_decimal_places: Number(e.target.value) })}
        />
      </Field>
      <Field label="Date format">
        <TextInput value={config.date_format} onChange={(e) => updateConfig({ date_format: e.target.value })} />
      </Field>
    </PanelSection>
  )
}
