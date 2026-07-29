import { useRaceConfig } from '../../../hooks/useRaceConfig'
import { useRenderJob } from '../../../hooks/useRenderJob'

export function ExportControls() {
  const { config } = useRaceConfig()
  const { status, error, startRender, downloadUrl } = useRenderJob()

  const isRendering = status && status.status !== 'done' && status.status !== 'failed'

  return (
    <div className="mt-2">
      <button
        type="button"
        disabled={Boolean(isRendering)}
        onClick={() => startRender(config)}
        className="w-full rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-500 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {isRendering ? 'Rendering…' : 'Export'}
      </button>

      {status && (
        <div className="mt-3">
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-gray-800">
            <div
              className="h-full bg-violet-500 transition-all"
              style={{ width: `${status.progress}%` }}
            />
          </div>
          <p className="mt-1 text-xs text-gray-400">
            {status.status} — {status.progress}%
          </p>
        </div>
      )}

      {error && <p className="mt-2 text-xs text-red-400">{error}</p>}

      {status?.status === 'done' && downloadUrl && (
        <a
          href={downloadUrl}
          download
          className="mt-3 block rounded-lg border border-gray-700 px-4 py-2 text-center text-sm font-medium text-gray-100 hover:bg-gray-800"
        >
          Download {config.export_format.toUpperCase()}
        </a>
      )}
    </div>
  )
}
