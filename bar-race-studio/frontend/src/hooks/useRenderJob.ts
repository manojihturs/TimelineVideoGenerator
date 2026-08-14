import { useCallback, useEffect, useRef, useState } from 'react'
import { createRender, getRenderStatus, renderDownloadUrl } from '../api/renders'
import type { RaceConfig } from '../models/RaceConfig'
import type { RenderJobStatus } from '../models/Frames'

const POLL_INTERVAL_MS = 1000

export function useRenderJob() {
  const [jobId, setJobId] = useState<string | null>(null)
  const [status, setStatus] = useState<RenderJobStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }, [])

  const startRender = useCallback(
    async (config: RaceConfig) => {
      setError(null)
      setStatus(null)
      try {
        const { job_id } = await createRender(config)
        setJobId(job_id)
        stopPolling()
        pollRef.current = setInterval(async () => {
          try {
            const s = await getRenderStatus(job_id)
            setStatus(s)
            if (s.status === 'done' || s.status === 'failed') {
              stopPolling()
              if (s.status === 'failed') setError(s.error ?? 'Render failed')
            }
          } catch (e) {
            stopPolling()
            setError(e instanceof Error ? e.message : 'Failed to check render status')
          }
        }, POLL_INTERVAL_MS)
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to start render')
      }
    },
    [stopPolling],
  )

  useEffect(() => {
    return () => {
      stopPolling()
    }
  }, [])

  return {
    jobId,
    status,
    error,
    startRender,
    downloadUrl: jobId ? renderDownloadUrl(jobId) : null,
  }
}
