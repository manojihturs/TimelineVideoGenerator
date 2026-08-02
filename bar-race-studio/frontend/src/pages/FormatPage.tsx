import { useCallback, useState } from 'react'
import { Link } from 'react-router-dom'
import { formatFiles, runAutoGenerateNow, type FormatMode, type FormatResult } from '../api/format'

const ACCEPT = '.csv,.xlsx,.xls'

type Action = 'format_only' | 'auto_generate' | 'run_now'

export function FormatPage() {
  const [files, setFiles] = useState<File[]>([])
  const [isDragging, setIsDragging] = useState(false)
  const [runningAction, setRunningAction] = useState<Action | null>(null)
  const [results, setResults] = useState<FormatResult[] | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const addFiles = useCallback((incoming: FileList | File[]) => {
    setResults(null)
    setNotice(null)
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

  async function handleFormat(mode: FormatMode) {
    if (files.length === 0) return
    const action: Action = mode
    setRunningAction(action)
    setError(null)
    setResults(null)
    setNotice(null)
    try {
      const outcome = await formatFiles(files, mode)
      setResults(outcome)
      setFiles((prev) => prev.filter((f) => !outcome.some((r) => r.filename === f.name && r.success)))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Format failed')
    } finally {
      setRunningAction(null)
    }
  }

  async function handleRunNow() {
    setRunningAction('run_now')
    setError(null)
    setNotice(null)
    try {
      await runAutoGenerateNow()
      setNotice('Started — processing whatever is currently in Unprocessed. Check back in a few minutes.')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not start auto-generate')
    } finally {
      setRunningAction(null)
    }
  }

  const isBusy = runningAction !== null

  return (
    <div className="mx-auto max-w-4xl px-6 py-12">
      <Link to="/" className="text-sm text-violet-400 hover:text-violet-300 hover:underline">
        &larr; Back to upload
      </Link>

      <h1 className="mb-1 mt-4 text-2xl font-semibold text-gray-100">Format Raw Datasets</h1>
      <p className="mb-8 text-sm text-gray-400">
        Drop any unformatted CSV or Excel files — each is reshaped into the app's template (Entity
        Name / Category / Image URL + one column per period).
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

      <div className="mt-6 grid gap-4 sm:grid-cols-3">
        <div className="rounded-lg border border-gray-800 p-4">
          <p className="mb-1 text-sm font-medium text-gray-100">Format</p>
          <p className="mb-3 text-xs text-gray-400">
            Just reshape and save to <code className="rounded bg-gray-800 px-1 py-0.5">uploads/Format</code>.
            Nothing gets rendered.
          </p>
          <button
            onClick={() => handleFormat('format_only')}
            disabled={files.length === 0 || isBusy}
            className="w-full rounded-lg bg-gray-700 px-4 py-2 text-sm font-medium text-white hover:bg-gray-600 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {runningAction === 'format_only' ? 'Formatting…' : `Format ${files.length || ''} File${files.length === 1 ? '' : 's'}`}
          </button>
        </div>

        <div className="rounded-lg border border-violet-800 bg-violet-500/5 p-4">
          <p className="mb-1 text-sm font-medium text-gray-100">Format &amp; Auto Generate</p>
          <p className="mb-3 text-xs text-gray-400">
            Reshape and save to <code className="rounded bg-gray-800 px-1 py-0.5">uploads/Unprocessed</code> —
            picked up automatically and rendered into a 5-minute desktop video and 60-second mobile
            short.
          </p>
          <button
            onClick={() => handleFormat('auto_generate')}
            disabled={files.length === 0 || isBusy}
            className="w-full rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-500 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {runningAction === 'auto_generate' ? 'Formatting…' : `Format & Generate ${files.length || ''}`}
          </button>
        </div>

        <div className="rounded-lg border border-gray-800 p-4">
          <p className="mb-1 text-sm font-medium text-gray-100">Auto-Generate</p>
          <p className="mb-3 text-xs text-gray-400">
            No upload needed — processes whatever's already sitting in{' '}
            <code className="rounded bg-gray-800 px-1 py-0.5">uploads/Unprocessed</code> right now,
            instead of waiting for the next automatic check.
          </p>
          <button
            onClick={handleRunNow}
            disabled={isBusy}
            className="w-full rounded-lg bg-gray-700 px-4 py-2 text-sm font-medium text-white hover:bg-gray-600 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {runningAction === 'run_now' ? 'Starting…' : 'Auto-Generate Now'}
          </button>
        </div>
      </div>

      {error && <p className="mt-4 text-sm text-red-400">{error}</p>}
      {notice && <p className="mt-4 text-sm text-emerald-400">{notice}</p>}

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
                <span> &rarr; saved as {r.saved_as}</span>
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
