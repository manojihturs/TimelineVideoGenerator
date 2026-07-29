import { ChartTextPanel } from './panels/ChartTextPanel'
import { AnimationPanel } from './panels/AnimationPanel'
import { BarsPanel } from './panels/BarsPanel'
import { LabelsPanel } from './panels/LabelsPanel'
import { FormattingPanel } from './panels/FormattingPanel'
import { ImagesPanel } from './panels/ImagesPanel'
import { ExportPanel } from './panels/ExportPanel'

/** Left pane of the studio — every RaceConfig field lives in exactly one
 * of these section panels, each reading/writing via useRaceConfig. */
export function PropertyPanel() {
  return (
    <div>
      <ChartTextPanel />
      <BarsPanel />
      <AnimationPanel />
      <LabelsPanel />
      <FormattingPanel />
      <ImagesPanel />
      <ExportPanel />
    </div>
  )
}
