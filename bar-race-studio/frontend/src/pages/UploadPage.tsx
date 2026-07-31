import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { DropzoneUpload } from '../components/upload/DropzoneUpload'
import { uploadDataset } from '../api/uploads'

export function UploadPage() {
  const navigate = useNavigate()
  const [error, setError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)

  async function handleFile(file: File) {
    setError(null)
    setIsLoading(true)
    try {
      const uploaded = await uploadDataset(file)
      navigate(`/mapping/${uploaded.dataset_id}`)
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

      <a
        href="/csv_template.csv"
        download
        className="mt-3 inline-block text-sm text-violet-400 hover:text-violet-300 hover:underline"
      >
        Download a sample CSV template
      </a>

      {isLoading && <p className="mt-4 text-sm text-gray-400">Uploading…</p>}
      {error && <p className="mt-4 text-sm text-red-400">{error}</p>}
    </div>
  )
}
