import { useState } from 'react'
import { useRaceConfig } from '../../../hooks/useRaceConfig'
import { uploadWatermark } from '../../../api/assets'
import type { WatermarkPosition } from '../../../models/RaceConfig'
import { Field, NumberInput, PanelSection, SelectInput } from '../FormControls'

const POSITION_OPTIONS: { value: WatermarkPosition; label: string }[] = [
  { value: 'top_left', label: 'Top left' },
  { value: 'top_right', label: 'Top right' },
  { value: 'bottom_left', label: 'Bottom left' },
  { value: 'bottom_right', label: 'Bottom right' },
]

export function WatermarkPanel() {
  const { config, updateConfig } = useRaceConfig()
  const [isUploading, setIsUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleFile(file: File) {
    setError(null)
    setIsUploading(true)
    try {
      const { asset_id } = await uploadWatermark(file)
      updateConfig({ watermark_asset_id: asset_id })
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Upload failed')
    } finally {
      setIsUploading(false)
    }
  }

  return (
    <PanelSection title="Watermark / logo">
      <label className="mb-3 block cursor-pointer rounded-md border border-dashed border-gray-700 px-3 py-2 text-center text-xs text-gray-400 hover:border-violet-500">
        {isUploading ? 'Uploading…' : config.watermark_asset_id ? 'Replace watermark image' : 'Upload watermark/logo image'}
        <input
          type="file"
          accept=".png,.jpg,.jpeg,.svg,.webp"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0]
            if (file) handleFile(file)
          }}
        />
      </label>
      {error && <p className="mb-2 text-xs text-red-400">{error}</p>}
      {config.watermark_asset_id && (
        <>
          <div className="mb-2 flex items-center gap-2">
            <img
              src={`/api/assets/${config.watermark_asset_id}`}
              alt="Watermark preview"
              className="h-10 w-10 rounded border border-gray-700 object-contain bg-gray-900"
            />
            <button
              type="button"
              onClick={() => updateConfig({ watermark_asset_id: null })}
              className="text-xs text-red-400 hover:underline"
            >
              Remove
            </button>
          </div>
          <Field label="Position">
            <SelectInput value={config.watermark_position} onChange={(value) => updateConfig({ watermark_position: value })} options={POSITION_OPTIONS} />
          </Field>
          <Field label="Opacity">
            <NumberInput
              min={0}
              max={1}
              step={0.05}
              value={config.watermark_opacity}
              onChange={(e) => updateConfig({ watermark_opacity: Number(e.target.value) })}
            />
          </Field>
          <Field label="Size (fraction of frame width)">
            <NumberInput
              min={0.02}
              max={0.5}
              step={0.01}
              value={config.watermark_scale}
              onChange={(e) => updateConfig({ watermark_scale: Number(e.target.value) })}
            />
          </Field>
        </>
      )}
    </PanelSection>
  )
}
