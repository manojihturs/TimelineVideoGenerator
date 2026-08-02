import { apiRequest } from './client'

export interface FormatResult {
  filename: string
  success: boolean
  saved_as: string | null
  error: string | null
}

export type FormatMode = 'format_only' | 'auto_generate'

export function formatFiles(files: File[], mode: FormatMode): Promise<FormatResult[]> {
  const formData = new FormData()
  for (const file of files) formData.append('files', file)
  formData.append('mode', mode)
  return apiRequest<FormatResult[]>('/api/format', { method: 'POST', body: formData })
}

export function runAutoGenerateNow(): Promise<{ status: string }> {
  return apiRequest<{ status: string }>('/api/format/run-now', { method: 'POST' })
}
