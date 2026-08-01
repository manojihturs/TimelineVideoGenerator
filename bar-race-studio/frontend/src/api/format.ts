import { apiRequest } from './client'

export interface FormatResult {
  filename: string
  success: boolean
  saved_as: string | null
  error: string | null
}

export function formatFiles(files: File[]): Promise<FormatResult[]> {
  const formData = new FormData()
  for (const file of files) formData.append('files', file)
  return apiRequest<FormatResult[]>('/api/format', { method: 'POST', body: formData })
}
