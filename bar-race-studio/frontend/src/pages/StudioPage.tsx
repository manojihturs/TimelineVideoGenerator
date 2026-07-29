import { useLocation, useParams } from 'react-router-dom'
import { AppShell } from '../components/layout/AppShell'
import { PropertyPanel } from '../components/settings/PropertyPanel'
import { RacePreviewPlayer } from '../components/preview-canvas/RacePreviewPlayer'
import { TimelineScrubber } from '../components/preview-canvas/TimelineScrubber'
import { RaceConfigProvider } from '../hooks/useRaceConfig'
import { createDefaultRaceConfig } from '../models/RaceConfig'
import type { DetectedColumns } from '../models/DatasetSchema'

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
      <AppShell
        header={<span className="text-sm font-medium text-gray-200">Bar Race Studio</span>}
        left={<PropertyPanel />}
        center={<RacePreviewPlayer />}
        bottom={<TimelineScrubber periods={detected.value_columns} />}
      />
    </RaceConfigProvider>
  )
}
