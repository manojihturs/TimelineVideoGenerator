import { apiRequest } from './client'
import type { DatasetPreview, DetectedColumns, UploadResponse } from '../models/DatasetSchema'

export function uploadDataset(file: File): Promise<UploadResponse> {
  const formData = new FormData()
  formData.append('file', file)
  return apiRequest<UploadResponse>('/api/uploads', { method: 'POST', body: formData })
}

export function detectColumns(datasetId: string): Promise<DetectedColumns> {
  return apiRequest<DetectedColumns>(`/api/uploads/${datasetId}/detect-columns`, { method: 'POST' })
}

export function previewDataset(datasetId: string): Promise<DatasetPreview> {
  return apiRequest<DatasetPreview>(`/api/uploads/${datasetId}/preview`, { method: 'POST' })
}
