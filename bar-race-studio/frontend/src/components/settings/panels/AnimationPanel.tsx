import { useRaceConfig } from '../../../hooks/useRaceConfig'
import type { Interpolation } from '../../../models/RaceConfig'
import { Field, NumberInput, PanelSection, SelectInput, ToggleInput } from '../FormControls'

const INTERPOLATION_OPTIONS: { value: Interpolation; label: string }[] = [
  { value: 'linear', label: 'Linear' },
  { value: 'easeInOut', label: 'Ease in/out' },
  { value: 'easeIn', label: 'Ease in' },
  { value: 'easeOut', label: 'Ease out' },
]

export function AnimationPanel() {
  const { config, updateConfig } = useRaceConfig()
  return (
    <PanelSection title="Animation">
      <Field label="Frames per second">
        <NumberInput
          min={1}
          max={60}
          value={config.fps}
          onChange={(e) => updateConfig({ fps: Number(e.target.value) })}
        />
      </Field>
      <Field label="Animation speed">
        <NumberInput
          min={0.1}
          step={0.1}
          value={config.animation_speed}
          onChange={(e) => updateConfig({ animation_speed: Number(e.target.value) })}
        />
      </Field>
      <Field label="Transition duration (ms)">
        <NumberInput
          min={0}
          step={50}
          value={config.transition_duration_ms}
          onChange={(e) => updateConfig({ transition_duration_ms: Number(e.target.value) })}
        />
      </Field>
      <Field label="Interpolation">
        <SelectInput
          value={config.interpolation}
          onChange={(value) => updateConfig({ interpolation: value })}
          options={INTERPOLATION_OPTIONS}
        />
      </Field>
      <ToggleInput
        label="Smooth animation"
        checked={config.smooth_animation}
        onChange={(checked) => updateConfig({ smooth_animation: checked })}
      />
    </PanelSection>
  )
}
