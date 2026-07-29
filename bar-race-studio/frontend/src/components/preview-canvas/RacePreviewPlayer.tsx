import { useRaceConfig } from '../../hooks/useRaceConfig'
import type { FrameRow } from '../../models/Frames'
import { formatValue } from '../../utils/formatters'

interface Props {
  frame: FrameRow[]
  isLoading: boolean
  error: string | null
}

/** Renders the real ranked/interpolated data for one frame (from
 * usePreviewFrames + TimelineScrubber's current position) using the same
 * settings the final matplotlib renderer honors — orientation, color
 * mode grouping, labels — so what you see here previews the real
 * output, not a decorative stand-in. */
export function RacePreviewPlayer({ frame, isLoading, error }: Props) {
  const { config } = useRaceConfig()
  const isVertical = config.orientation === 'vertical'
  const maxValue = Math.max(1, ...frame.map((f) => f.value))
  const sorted = [...frame].sort((a, b) => a.rank - b.rank)

  return (
    <div
      className="flex aspect-video w-full max-w-3xl flex-col gap-2 rounded-lg border border-gray-800 p-6"
      style={{ backgroundColor: config.background_color, fontFamily: config.font_family }}
    >
      {config.title && <h2 className="text-lg font-semibold text-gray-100">{config.title}</h2>}
      {config.subtitle && <p className="text-sm text-gray-400">{config.subtitle}</p>}

      {error && <p className="text-sm text-red-400">{error}</p>}
      {!error && isLoading && frame.length === 0 && (
        <p className="mt-4 text-center text-sm text-gray-500">Loading preview…</p>
      )}

      <div className={`mt-2 flex flex-1 gap-3 ${isVertical ? 'items-end justify-center' : 'flex-col justify-center'}`}>
        {sorted.map((row) => {
          const pct = Math.max(2, (row.value / maxValue) * 100)
          return (
            <div key={row.entity} className={`flex items-center gap-2 ${isVertical ? 'flex-col-reverse' : ''}`}>
              {config.show_rank && !isVertical && (
                <span className="w-5 shrink-0 text-right text-xs font-bold text-gray-500">{row.rank}</span>
              )}
              <div
                className={isVertical ? 'w-10' : 'flex-1'}
                style={isVertical ? { height: `${pct}%` } : undefined}
              >
                <div
                  className="rounded bg-violet-500"
                  style={
                    isVertical
                      ? { height: '100%', width: '100%' }
                      : { height: `${config.label_size_px + 10}px`, width: `${pct}%` }
                  }
                />
              </div>
              <span className="whitespace-nowrap text-xs text-gray-200">
                {row.entity}
                {config.show_category && row.category ? ` (${row.category})` : ''}
                {config.show_value ? ` — ${formatValue(row.value, config.value_format, config.value_decimal_places)}` : ''}
              </span>
            </div>
          )
        })}
      </div>

      {config.data_source_label && (
        <p className="mt-2 text-right text-xs text-gray-500">Source: {config.data_source_label}</p>
      )}
    </div>
  )
}
