import { apiRequest } from './client'
import type { FramesResponse, RenderJobResponse, RenderJobStatus } from '../models/Frames'
import type { RaceConfig } from '../models/RaceConfig'

export function fetchPreviewFrames(config: RaceConfig): Promise<FramesResponse> {
  return apiRequest<FramesResponse>('/api/renders/preview-frames', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  })
}

export function createRender(config: RaceConfig): Promise<RenderJobResponse> {
  return apiRequest<RenderJobResponse>('/api/renders', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  })
}

export function getRenderStatus(jobId: string): Promise<RenderJobStatus> {
  return apiRequest<RenderJobStatus>(`/api/renders/${jobId}`)
}

export function renderDownloadUrl(jobId: string): string {
  return `/api/renders/${jobId}/download`
}
