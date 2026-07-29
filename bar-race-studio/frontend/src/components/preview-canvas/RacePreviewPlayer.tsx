import { useRaceConfig } from '../../hooks/useRaceConfig'

/** Placeholder for the live preview canvas — actual frame rendering is
 * Phase 4 (race_renderer.py + a real preview pipeline). For now this
 * reflects the current RaceConfig so the studio shell is testable
 * end-to-end before rendering exists. */
export function RacePreviewPlayer() {
  const { config } = useRaceConfig()
  const isVertical = config.orientation === 'vertical'

  return (
    <div
      className="flex aspect-video w-full max-w-3xl flex-col justify-center gap-2 rounded-lg border border-gray-800 p-6"
      style={{ backgroundColor: config.background_color, fontFamily: config.font_family }}
    >
      {config.title && <h2 className="text-lg font-semibold text-gray-100">{config.title}</h2>}
      {config.subtitle && <p className="text-sm text-gray-400">{config.subtitle}</p>}

      <div className={`mt-4 flex flex-1 gap-2 ${isVertical ? 'items-end' : 'flex-col justify-end'}`}>
        {Array.from({ length: Math.min(config.bar_count, 6) }).map((_, i) => {
          const size = 90 - i * 12
          return (
            <div
              key={i}
              className="rounded bg-violet-500/70"
              style={
                isVertical
                  ? { width: '14%', height: `${size}%` }
                  : { height: `${config.label_size_px + 8}px`, width: `${size}%` }
              }
            />
          )
        })}
      </div>

      {config.data_source_label && (
        <p className="mt-2 text-right text-xs text-gray-500">Source: {config.data_source_label}</p>
      )}

      <p className="mt-2 text-center text-xs text-gray-600">
        Preview placeholder — real rendering lands in Phase 4
      </p>
    </div>
  )
}
