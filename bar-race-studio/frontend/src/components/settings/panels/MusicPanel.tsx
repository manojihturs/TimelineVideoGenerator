import { useState } from 'react'
import { useRaceConfig } from '../../../hooks/useRaceConfig'
import { uploadMusic } from '../../../api/assets'
import { Field, NumberInput, PanelSection } from '../FormControls'

export function MusicPanel() {
  const { config, updateConfig } = useRaceConfig()
  const [isUploading, setIsUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [fileName, setFileName] = useState<string | null>(null)

  async function handleFile(file: File) {
    setError(null)
    setIsUploading(true)
    try {
      const { asset_id } = await uploadMusic(file)
      updateConfig({ music_asset_id: asset_id })
      setFileName(file.name)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Upload failed')
    } finally {
      setIsUploading(false)
    }
  }

  return (
    <PanelSection title="Background music">
      <label className="mb-3 block cursor-pointer rounded-md border border-dashed border-gray-700 px-3 py-2 text-center text-xs text-gray-400 hover:border-violet-500">
        {isUploading ? 'Uploading…' : config.music_asset_id ? `Replace track${fileName ? ` (${fileName})` : ''}` : 'Upload background music'}
        <input
          type="file"
          accept=".mp3,.wav,.m4a,.aac,.ogg"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0]
            if (file) handleFile(file)
          }}
        />
      </label>
      {error && <p className="mb-2 text-xs text-red-400">{error}</p>}
      {config.music_asset_id && (
        <>
          <button
            type="button"
            onClick={() => {
              updateConfig({ music_asset_id: null })
              setFileName(null)
            }}
            className="mb-2 text-xs text-red-400 hover:underline"
          >
            Remove
          </button>
          <Field label="Volume">
            <NumberInput
              min={0}
              max={1}
              step={0.05}
              value={config.music_volume}
              onChange={(e) => updateConfig({ music_volume: Number(e.target.value) })}
            />
          </Field>
        </>
      )}
      <p className="mt-1 text-xs text-gray-500">
        Only upload music you have the rights to use — this is mixed directly into the exported video.
      </p>
    </PanelSection>
  )
}
