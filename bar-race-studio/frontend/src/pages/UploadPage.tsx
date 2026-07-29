import { useState } from 'react'
import { DropzoneUpload } from '../components/upload/DropzoneUpload'
import { DataPreviewTable } from '../components/preview/DataPreviewTable'
import { ColumnMappingScreen } from '../components/mapping/ColumnMappingScreen'
import { detectColumns, previewDataset, uploadDataset } from '../api/uploads'
import type { DatasetPreview, DetectedColumns, UploadResponse } from '../models/DatasetSchema'

export function UploadPage() {
  const [upload, setUpload] = useState<UploadResponse | null>(null)
  const [detected, setDetected] = useState<DetectedColumns | null>(null)
  const [preview, setPreview] = useState<DatasetPreview | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)

  async function handleFile(file: File) {
    setError(null)
    setIsLoading(true)
    try {
      const uploaded = await uploadDataset(file)
      setUpload(uploaded)
      const [detectedColumns, previewData] = await Promise.all([
        detectColumns(uploaded.dataset_id),
        previewDataset(uploaded.dataset_id),
      ])
      setDetected(detectedColumns)
      setPreview(previewData)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Upload failed')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="mx-auto max-w-4xl px-6 py-12">
      <h1 className="mb-1 text-2xl font-semibold text-gray-100">Bar Race Studio</h1>
      <p className="mb-8 text-sm text-gray-400">
        Upload any CSV or XLSX dataset — columns are detected automatically.
      </p>

      <DropzoneUpload onFileSelected={handleFile} />

      {isLoading && <p className="mt-4 text-sm text-gray-400">Analyzing dataset…</p>}
      {error && <p className="mt-4 text-sm text-red-400">{error}</p>}

      {upload && (
        <p className="mt-6 text-sm text-gray-400">
          <span className="font-medium text-gray-200">{upload.filename}</span> — {upload.row_count} rows,{' '}
          {upload.columns.length} columns
        </p>
      )}

      {detected && (
        <div className="mt-4">
          <ColumnMappingScreen columns={upload?.columns ?? []} detected={detected} />
        </div>
      )}

      {preview && (
        <div className="mt-6">
          <h3 className="mb-2 text-sm font-semibold text-gray-300">Preview (first {preview.rows.length} rows)</h3>
          <DataPreviewTable preview={preview} />
        </div>
      )}
    </div>
  )
}
