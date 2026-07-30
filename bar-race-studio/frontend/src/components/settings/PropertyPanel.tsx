import { ChartTextPanel } from './panels/ChartTextPanel'
import { StylePanel } from './panels/StylePanel'
import { AnimationPanel } from './panels/AnimationPanel'
import { BarsPanel } from './panels/BarsPanel'
import { LabelsPanel } from './panels/LabelsPanel'
import { FormattingPanel } from './panels/FormattingPanel'
import { ImagesPanel } from './panels/ImagesPanel'
import { WatermarkPanel } from './panels/WatermarkPanel'
import { MusicPanel } from './panels/MusicPanel'
import { ExportPanel } from './panels/ExportPanel'
import { ProjectPanel } from './panels/ProjectPanel'

/** Left pane of the studio — every RaceConfig field lives in exactly one
 * of these section panels, each reading/writing via useRaceConfig. */
export function PropertyPanel() {
  return (
    <div>
      <ChartTextPanel />
      <StylePanel />
      <BarsPanel />
      <AnimationPanel />
      <LabelsPanel />
      <FormattingPanel />
      <ImagesPanel />
      <WatermarkPanel />
      <MusicPanel />
      <ExportPanel />
      <ProjectPanel />
    </div>
  )
}
