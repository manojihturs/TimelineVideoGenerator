import { useState } from 'react'
import { useLocation, useParams } from 'react-router-dom'
import { AppShell } from '../components/layout/AppShell'
import { PropertyPanel } from '../components/settings/PropertyPanel'
import { RacePreviewPlayer } from '../components/preview-canvas/RacePreviewPlayer'
import { TimelineScrubber } from '../components/preview-canvas/TimelineScrubber'
import { RaceConfigProvider, useRaceConfig } from '../hooks/useRaceConfig'
import { usePreviewFrames } from '../hooks/usePreviewFrames'
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
  const detected = location.state?.detected as DetectedColumns | undefined

  if (!datasetId || !detected?.entity_column) {
    return (
      <div className="p-12 text-center text-sm text-gray-400">
        Missing dataset mapping — go back and upload a file first.
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
