export interface FrameRow {
  frame_index: number
  entity: string
  category: string | null
  image_url: string | null
  value: number
  rank: number
}

export interface FramesResponse {
  frame_count: number
  frames: FrameRow[]
}

export interface RenderJobResponse {
  job_id: string
}

export type RenderStatus = 'queued' | 'rendering' | 'encoding' | 'done' | 'failed'

export interface RenderJobStatus {
  status: RenderStatus
  progress: number
  error: string | null
}
