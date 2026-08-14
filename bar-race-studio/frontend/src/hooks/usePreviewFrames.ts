import { useEffect, useRef, useState } from 'react'
import { fetchPreviewFrames } from '../api/renders'
import type { RaceConfig } from '../models/RaceConfig'
import type { FrameRow } from '../models/Frames'

const DEBOUNCE_MS = 400

/** Fetches real ranked/interpolated frame data from the Phase 3 pipeline
 * whenever a setting that changes the *data* (not just visual styling)
 * changes — debounced so dragging a slider doesn't fire a request per
 * pixel. */
export function usePreviewFrames(config: RaceConfig) {
  const [frames, setFrames] = useState<FrameRow[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const requestIdRef = useRef(0)

  const dataKey = JSON.stringify({
    dataset_id: config.dataset_id,
    mapping: config.mapping,
    bar_count: config.bar_count,
    sort_direction: config.sort_direction,
    smooth_animation: config.smooth_animation,
    interpolation: config.interpolation,
  })

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      setIsLoading(true)
      setError(null)
      const requestId = ++requestIdRef.current
      fetchPreviewFrames(config)
        .then((res) => {
          if (requestIdRef.current !== requestId) return
          setFrames(res.frames)
        })
        .catch((e) => {
          if (requestIdRef.current !== requestId) return
          setError(e instanceof Error ? e.message : 'Failed to load preview')
        })
        .finally(() => {
          if (requestIdRef.current !== requestId) return
          setIsLoading(false)
        })
    }, DEBOUNCE_MS)
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dataKey])

  const frameIndices = Array.from(new Set(frames.map((f) => f.frame_index))).sort((a, b) => a - b)

  return { frames, frameIndices, isLoading, error }
}
