import { apiRequest } from './client'
import type { RaceConfig } from '../models/RaceConfig'

export interface ProjectSummary {
  id: string
  name: string
  dataset_id: string
  created_at: string
  updated_at: string
}

export interface ProjectDetail extends ProjectSummary {
  config: RaceConfig
}

export function saveProject(name: string, config: RaceConfig, projectId?: string): Promise<{ project_id: string }> {
  return apiRequest('/api/projects', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, config, project_id: projectId ?? null }),
  })
}

export function listProjects(): Promise<ProjectSummary[]> {
  return apiRequest('/api/projects')
}

export function getProject(projectId: string): Promise<ProjectDetail> {
  return apiRequest(`/api/projects/${projectId}`)
}
