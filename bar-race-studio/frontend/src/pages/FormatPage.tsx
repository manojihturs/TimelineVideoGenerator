import { useCallback, useState } from 'react'
import { Link } from 'react-router-dom'
import { formatFiles, type FormatResult } from '../api/format'

const ACCEPT = '.csv,.xlsx,.xls'

export function FormatPage() {
  const [files, setFiles] = useState<File[]>([])
  const [isDragging, setIsDragging] = useState(false)
  const [isFormatting, setIsFormatting] = useState(false)
  const [results, setResults] = useState<FormatResult[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  const addFiles = useCallback((incoming: FileList | File[]) => {
    setResults(null)
    setError(null)
    setFiles((prev) => {
      const existingNames = new Set(prev.map((f) => f.name))
      const next = [...prev]
      for (const file of Array.from(incoming)) {
        if (!existingNames.has(file.name)) next.push(file)
      }
      return next
    })
  }, [])

  function removeFile(name: string) {
    setFiles((prev) => prev.filter((f) => f.name !== name))
  }

  async function handleFormat() {
    if (files.length === 0) return
    setIsFormatting(true)
    setError(null)
    setResults(null)
    try {
      const outcome = await formatFiles(files)
      setResults(outcome)
      setFiles((prev) => prev.filter((f) => !outcome.some((r) => r.filename === f.name && r.success)))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Format failed')
    } finally {
      setIsFormatting(false)
    }
  }

  return (
    <div className="mx-auto max-w-4xl px-6 py-12">
      <Link to="/" className="text-sm text-violet-400 hover:text-violet-300 hover:underline">
        &larr; Back to upload
      </Link>

      <h1 className="mb-1 mt-4 text-2xl font-semibold text-gray-100">Format Raw Datasets</h1>
      <p className="mb-8 text-sm text-gray-400">
        Drop any unformatted CSV or Excel files — each is reshaped into the app's template (Entity
        Name / Category / Image URL + one column per period) and saved to{' '}
        <code className="rounded bg-gray-800 px-1 py-0.5 text-xs">storage/uploads/Unprocessed</code>.
        Files placed there are picked up automatically and rendered into a 5-minute desktop video
        and a 60-second mobile short, then moved to <code className="rounded bg-gray-800 px-1 py-0.5 text-xs">Processed</code>{' '}
        (or <code className="rounded bg-gray-800 px-1 py-0.5 text-xs">Failed</code> with an error note, if
        something didn't work).
      </p>

      <div
        onDragOver={(e) => {
          e.preventDefault()
          setIsDragging(true)
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={(e) => {
          e.preventDefault()
          setIsDragging(false)
          if (e.dataTransfer.files.length) addFiles(e.dataTransfer.files)
        }}
        className={`flex flex-col items-center justify-center rounded-xl border-2 border-dashed p-16 text-center transition-colors ${
          isDragging ? 'border-violet-400 bg-violet-500/10' : 'border-gray-700 bg-gray-900/40'
        }`}
      >
        <p className="mb-2 text-lg font-medium text-gray-100">Drag &amp; drop CSV or Excel files</p>
        <p className="mb-4 text-sm text-gray-400">or</p>
        <label className="cursor-pointer rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-500">
          Browse files
          <input
            type="file"
            accept={ACCEPT}
            multiple
            className="hidden"
            onChange={(e) => {
              if (e.target.files?.length) addFiles(e.target.files)
              e.target.value = ''
            }}
          />
        </label>
      </div>

      {files.length > 0 && (
        <ul className="mt-6 divide-y divide-gray-800 rounded-lg border border-gray-800">
          {files.map((file) => (
            <li key={file.name} className="flex items-center justify-between px-4 py-2 text-sm text-gray-200">
              <span>{file.name}</span>
              <button
                onClick={() => removeFile(file.name)}
                className="text-gray-500 hover:text-red-400"
                aria-label={`Remove ${file.name}`}
              >
                &times;
              </button>
            </li>
          ))}
        </ul>
      )}

      <button
        onClick={handleFormat}
        disabled={files.length === 0 || isFormatting}
        className="mt-6 rounded-lg bg-violet-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-violet-500 disabled:cursor-not-allowed disabled:opacity-40"
      >
        {isFormatting ? 'Formatting…' : `Format ${files.length || ''} File${files.length === 1 ? '' : 's'}`}
      </button>

      {error && <p className="mt-4 text-sm text-red-400">{error}</p>}

      {results && (
        <ul className="mt-6 space-y-2">
          {results.map((r) => (
            <li
              key={r.filename}
              className={`rounded-lg border px-4 py-3 text-sm ${
                r.success ? 'border-emerald-800 bg-emerald-950/40 text-emerald-300' : 'border-red-900 bg-red-950/40 text-red-300'
              }`}
            >
              <span className="font-medium">{r.filename}</span>
              {r.success ? (
                <span> &rarr; saved as {r.saved_as}, queued for auto-rendering</span>
              ) : (
                <span> &mdash; {r.error}</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
