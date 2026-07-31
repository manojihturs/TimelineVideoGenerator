import { useEffect, useState } from 'react'
import { useLocation, useParams } from 'react-router-dom'
import { AppShell } from '../components/layout/AppShell'
import { PropertyPanel } from '../components/settings/PropertyPanel'
import { RacePreviewPlayer } from '../components/preview-canvas/RacePreviewPlayer'
import { TimelineScrubber } from '../components/preview-canvas/TimelineScrubber'
import { RaceConfigProvider, useRaceConfig } from '../hooks/useRaceConfig'
import { usePreviewFrames } from '../hooks/usePreviewFrames'
import { detectColumns } from '../api/uploads'
import { createDefaultRaceConfig } from '../models/RaceConfig'
import type { DetectedColumns } from '../models/DatasetSchema'

function StudioContent() {
  const { config } = useRaceConfig()
  const { frames, frameIndices, isLoading, error } = usePreviewFrames(config)
  const [scrubIndex, setScrubIndex] = useState(0)

  const currentFrameIndex = frameIndices[Math.min(scrubIndex, frameIndices.length - 1)]
  const currentFrame = frames.filter((f) => f.frame_index === currentFrameIndex)

  const periodLabel = (frameIndex: number) => {
    const cols = config.mapping.value_columns
    const lo = Math.floor(frameIndex)
    const hi = Math.min(lo + 1, cols.length - 1)
    const frac = frameIndex - lo
    return cols[frac < 0.5 ? lo : hi] ?? cols[0] ?? ''
  }

  return (
    <AppShell
      header={<span className="text-sm font-medium text-gray-200">Bar Race Studio</span>}
      left={<PropertyPanel />}
      center={<RacePreviewPlayer frame={currentFrame} isLoading={isLoading} error={error} />}
      bottom={
        <TimelineScrubber
          frameIndices={frameIndices}
          currentIndex={scrubIndex}
          onChange={setScrubIndex}
          periodLabel={periodLabel}
        />
      }
    />
  )
}

export function StudioPage() {
  const { datasetId } = useParams<{ datasetId: string }>()
  const location = useLocation()
  const stateDetected = location.state?.detected as DetectedColumns | undefined

  // location.state is only populated when arriving via MappingPage's
  // in-app navigation — it does not survive a page refresh, a directly
  // opened/bookmarked /studio/:datasetId URL, or a new tab. Re-detecting
  // columns from the dataset_id already in the URL whenever state is
  // missing makes this page work the same way regardless of how it was
  // reached, instead of only working right after the mapping step.
  const [fetchedDetected, setFetchedDetected] = useState<DetectedColumns | null>(null)
  const [fetchError, setFetchError] = useState<string | null>(null)
  const [isFetching, setIsFetching] = useState(!stateDetected)

  useEffect(() => {
    if (stateDetected || !datasetId) return
    setIsFetching(true)
    setFetchError(null)
    detectColumns(datasetId)
      .then(setFetchedDetected)
      .catch((e) => setFetchError(e instanceof Error ? e.message : 'Failed to load dataset'))
      .finally(() => setIsFetching(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [datasetId])

  const detected = stateDetected ?? fetchedDetected

  if (!datasetId) {
    return <div className="p-12 text-center text-sm text-gray-400">No dataset selected.</div>
  }

  if (isFetching) {
    return <div className="p-12 text-center text-sm text-gray-400">Loading dataset…</div>
  }

  if (fetchError) {
    return (
      <div className="p-12 text-center text-sm text-red-400">
        Could not load this dataset ({fetchError}). It may have been removed — try uploading it again.
      </div>
    )
  }

  if (!detected?.entity_column) {
    return (
      <div className="p-12 text-center text-sm text-gray-400">
        This dataset has no usable entity column — go back and check the mapping.
      </div>
    )
  }

  const initialConfig = createDefaultRaceConfig({
    entity_column: detected.entity_column,
    category_column: detected.category_column,
    image_column: detected.image_column,
    timeline_start_column: detected.timeline_start_column ?? '',
    timeline_end_column: detected.timeline_end_column ?? '',
    value_columns: detected.value_columns,
  })
  initialConfig.dataset_id = datasetId

  return (
    <RaceConfigProvider initialConfig={initialConfig}>
      <StudioContent />
    </RaceConfigProvider>
  )
}
