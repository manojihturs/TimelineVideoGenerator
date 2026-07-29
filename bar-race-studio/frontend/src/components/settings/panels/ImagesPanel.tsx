import { useRaceConfig } from '../../../hooks/useRaceConfig'
import { PanelSection, ToggleInput } from '../FormControls'

export function ImagesPanel() {
  const { config, updateConfig } = useRaceConfig()
  const hasImageColumn = Boolean(config.mapping.image_column)
  return (
    <PanelSection title="Images">
      <ToggleInput
        label="Show images"
        checked={config.show_images}
        onChange={(v) => updateConfig({ show_images: v })}
      />
      {!hasImageColumn && (
        <p className="mt-1 text-xs text-gray-500">
          No image column detected — entities will show colored initials instead.
        </p>
      )}
    </PanelSection>
  )
}
