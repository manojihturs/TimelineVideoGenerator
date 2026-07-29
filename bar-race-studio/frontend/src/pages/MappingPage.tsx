import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ColumnMappingScreen } from '../components/mapping/ColumnMappingScreen'
import { DataPreviewTable } from '../components/preview/DataPreviewTable'
import { detectColumns, previewDataset } from '../api/uploads'
import type { DatasetPreview, DetectedColumns } from '../models/DatasetSchema'

export function MappingPage() {
  const { datasetId } = useParams<{ datasetId: string }>()
  const navigate = useNavigate()
  const [detected, setDetected] = useState<DetectedColumns | null>(null)
  const [preview, setPreview] = useState<DatasetPreview | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!datasetId) return
    Promise.all([detectColumns(datasetId), previewDataset(datasetId)])
      .then(([d, p]) => {
        setDetected(d)
        setPreview(p)
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to analyze dataset'))
  }, [datasetId])

  const canContinue = detected?.entity_column && detected.value_columns.length > 0

  return (
    <div className="mx-auto max-w-4xl px-6 py-12">
      <h1 className="mb-1 text-2xl font-semibold text-gray-100">Confirm column mapping</h1>
      <p className="mb-8 text-sm text-gray-400">
        Review the auto-detected columns before generating the race.
      </p>

      {error && <p className="mb-4 text-sm text-red-400">{error}</p>}

      {detected && (
        <div className="mb-6">
          <ColumnMappingScreen columns={preview?.columns ?? []} detected={detected} />
        </div>
      )}

      {preview && (
        <div className="mb-8">
          <h3 className="mb-2 text-sm font-semibold text-gray-300">Preview (first {preview.rows.length} rows)</h3>
          <DataPreviewTable preview={preview} />
        </div>
      )}

      <button
        type="button"
        disabled={!canContinue}
        onClick={() => datasetId && detected && navigate(`/studio/${datasetId}`, { state: { detected } })}
        className="rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-500 disabled:cursor-not-allowed disabled:opacity-40"
      >
        Continue to studio
      </button>
    </div>
  )
}
