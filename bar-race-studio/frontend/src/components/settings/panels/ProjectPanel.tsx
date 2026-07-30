import { useEffect, useState } from 'react'
import { useRaceConfig } from '../../../hooks/useRaceConfig'
import { getProject, listProjects, saveProject, type ProjectSummary } from '../../../api/projects'
import { Field, PanelSection, TextInput } from '../FormControls'

export function ProjectPanel() {
  const { config, setConfig } = useRaceConfig()
  const [name, setName] = useState('')
  const [projects, setProjects] = useState<ProjectSummary[]>([])
  const [status, setStatus] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  function refreshProjects() {
    listProjects().then(setProjects).catch(() => {})
  }

  useEffect(refreshProjects, [])

  async function handleSave() {
    setError(null)
    setStatus(null)
    if (!name.trim()) {
      setError('Enter a project name first')
      return
    }
    try {
      await saveProject(name.trim(), config)
      setStatus('Saved')
      refreshProjects()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Save failed')
    }
  }

  async function handleLoad(projectId: string) {
    setError(null)
    try {
      const project = await getProject(projectId)
      setConfig(project.config)
      setName(project.name)
      setStatus('Loaded')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Load failed')
    }
  }

  return (
    <PanelSection title="Saved projects">
      <Field label="Project name">
        <TextInput value={name} onChange={(e) => setName(e.target.value)} placeholder="My race video" />
      </Field>
      <button
        type="button"
        onClick={handleSave}
        className="mb-3 w-full rounded-md border border-gray-700 px-3 py-1.5 text-xs font-medium text-gray-100 hover:bg-gray-800"
      >
        Save current settings
      </button>
      {status && <p className="mb-2 text-xs text-emerald-400">{status}</p>}
      {error && <p className="mb-2 text-xs text-red-400">{error}</p>}

      {projects.length > 0 && (
        <div className="space-y-1">
          {projects.map((p) => (
            <button
              key={p.id}
              type="button"
              onClick={() => handleLoad(p.id)}
              className="block w-full truncate rounded px-2 py-1 text-left text-xs text-gray-300 hover:bg-gray-800"
              title={p.name}
            >
              {p.name}
            </button>
          ))}
        </div>
      )}
    </PanelSection>
  )
}
